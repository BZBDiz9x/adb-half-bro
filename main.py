import os
import sys
import subprocess
import threading
import tempfile
import shutil
import time
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk


class HorizontalVideoSplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("双屏视频生成器（adb)v1.12")
        self.root.geometry("500x300")
        self.root.resizable(False, False)

        self.video_path = ""
        self.devices = []
        self.temp_dir = None

        self._create_ui()
        self._check_environment()

    def _create_ui(self):
        #没啥可说的了，另外别删这一行注释，凑字用的doge
        tk.Label(self.root, text="双屏视频同步播放", font=("Arial", 16, "bold")).pack(pady=15)

        frame_file = tk.Frame(self.root)
        frame_file.pack(pady=10, fill=tk.X, padx=20)
        self.entry_file = tk.Entry(frame_file, width=30)
        self.entry_file.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Button(frame_file, text="浏览", command=self.browse_file).pack(side=tk.LEFT, padx=5)

        self.label_status = tk.Label(self.root, text="find...", fg="blue")
        self.label_status.pack(pady=5)
        tk.Button(self.root, text="刷新", command=self.refresh_devices).pack(pady=5)

        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=15)

        frame_btn = tk.Frame(self.root)
        frame_btn.pack(pady=10)
        self.btn_play = tk.Button(frame_btn, text="start", command=self.start_process,
                                  bg="#4CAF50", fg="white", state=tk.DISABLED)
        self.btn_play.pack(side=tk.LEFT, padx=10)

        tk.Button(frame_btn, text="clean", command=self.cleanup).pack(side=tk.LEFT, padx=10)

    def update_progress(self, value):
        self.progress['value'] = value
        self.root.update_idletasks()

    def _check_environment(self):
        try:
            subprocess.run(["adb", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            self.refresh_devices()
        except FileNotFoundError:
            messagebox.showerror("环境错误", " adb 和 ffmpeg都没有？？？")
            sys.exit(1)

    def browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov")])
        if path:
            self.video_path = path
            self.entry_file.delete(0, tk.END)
            self.entry_file.insert(0, path)
            self.btn_play.config(state=tk.NORMAL)

    def refresh_devices(self):
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')[1:]
            self.devices = [line.split('\t')[0] for line in lines if '\tdevice' in line]
            count = len(self.devices)
            if count == 0:
                self.label_status.config(text="啊哈...一台都没有是么？", fg="red")
            elif count < 2:
                self.label_status.config(text=f"检测到 {count} 台设备 (建议2台)", fg="orange")
            else:
                self.label_status.config(text=f"检测到 {count} 台设备 (就绪)", fg="green")
        except Exception:
            self.label_status.config(text="ADB 错误，自己找教程去", fg="red")

    def split_video_horizontal(self, input_path, output_dir):
        self.update_progress(10)
        probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-select_streams", "v:0",
                     input_path]
        try:
            result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            width = int(data['streams'][0]['width'])
            height = int(data['streams'][0]['height'])
        except Exception:
            return []

        part_width = width // 2
        video_parts = []
        offsets = [0, part_width]
        names = ["left", "right"]

        for i, (offset, name) in enumerate(zip(offsets, names)):
            self.update_progress(20 + i * 30)
            output_path = os.path.join(output_dir, f"{name}.mp4")
            filter_complex = f"crop={part_width}:{height}:{offset}:0"
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", filter_complex, "-c:a", "aac", "-b:a", "128k", "-movflags",
                   "+faststart", output_path]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(output_path):
                video_parts.append((name, output_path))

        self.update_progress(80)
        return video_parts

    def push_and_play(self, device_id, local_file, index):
        remote_path = f"/sdcard/Movies/split_part_{index}.mp4"
        subprocess.run(["adb", "-s", device_id, "push", local_file, remote_path], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        play_cmd = ["adb", "-s", device_id, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d",
                    f"file://{remote_path}", "-t", "video/mp4"]
        subprocess.Popen(play_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_process(self):
        if not self.video_path or not self.devices:
            return

        devices_to_use = self.devices[:2]
        if len(devices_to_use) < 2 and not messagebox.askyesno("就俩东西", "建议多买几台手机"):
            return

        self.btn_play.config(state=tk.DISABLED)
        self.temp_dir = tempfile.mkdtemp(prefix="video_split_")

        def task():
            try:
                parts = self.split_video_horizontal(self.video_path, self.temp_dir)
                if not parts:
                    raise Exception("拆分失败")

                threads = []
                for i, dev in enumerate(devices_to_use):
                    if i < len(parts):
                        t = threading.Thread(target=self.push_and_play, args=(dev, parts[i][1], i))
                        threads.append(t)
                        t.start()

                for t in threads:
                    t.join()

                self.update_progress(100)
                messagebox.showinfo("", "视频已分发并播放。")

            except Exception as e:
                messagebox.showerror("错误", str(e))
            finally:
                self.btn_play.config(state=tk.NORMAL)
                self.update_progress(0)

        threading.Thread(target=task, daemon=True).start()

    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
            messagebox.showinfo("清理", "大概是清理了吧...qaq")


if __name__ == "__main__":
    root = tk.Tk()
    app = HorizontalVideoSplitterApp(root)
    root.mainloop()
#丢github了，我打赌没人点star，更没人看这行
