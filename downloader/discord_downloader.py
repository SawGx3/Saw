#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
محمّل ملفات ديسكورد (Discord Collectibles Downloader)
- تحط الرابط، تختار الصيغة، ويحمّل لك الملف ويحوّله بخلفية شفافة.
- يدعم APNG المتحرك و WebM والصور الثابتة.
- الصيغ: MOV شفاف (ProRes 4444 / QuickTime Animation) ، WebM شفاف ، GIF شفاف ، PNG / الأصلي.

التشغيل: شغّل ملف "تشغيل.bat" (ويندوز) أو:  python discord_downloader.py
"""

import os
import re
import sys
import threading
import subprocess
import urllib.request

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------- مكتبات خارجية ----------
try:
    import numpy as np
    from PIL import Image, ImageSequence
    import imageio_ffmpeg
except ImportError as e:  # pragma: no cover
    msg = ("ينقص مكتبات. ثبّتها بالأمر:\n\n"
           "pip install Pillow numpy imageio-ffmpeg\n\n"
           f"التفاصيل: {e}")
    try:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("مكتبات ناقصة", msg)
    except Exception:
        print(msg)
    sys.exit(1)


FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# الصيغ المتاحة: الاسم المعروض -> (الامتداد, المعرّف الداخلي)
FORMATS = {
    "MOV شفاف — ProRes 4444 (للمونتاج، أعلى جودة)": (".mov", "prores"),
    "MOV شفاف — QuickTime Animation (أخف حجماً)": (".mov", "qtrle"),
    "WebM شفاف (للويب وديسكورد)": (".webm", "webm"),
    "GIF شفاف (توافق واسع)": (".gif", "gif"),
    "PNG / الملف الأصلي كما هو": (".png", "original"),
}


# =================== منطق التحميل والتحويل ===================

def http_get(url):
    """تحميل بايتات الرابط."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def is_apng(data):
    return data[:8] == b"\x89PNG\r\n\x1a\n" and b"acTL" in data[:65536]


def is_png(data):
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def is_webm(data):
    # EBML magic (matroska/webm)
    return data[:4] == b"\x1aE\xdf\xa3"


def load_frames_from_image(raw_path):
    """يقرأ APNG/PNG ويرجّع (frames RGBA, fps)."""
    im = Image.open(raw_path)
    frames, durs = [], []
    for fr in ImageSequence.Iterator(im):
        frames.append(np.array(fr.convert("RGBA")))
        d = fr.info.get("duration", 50)
        durs.append(d if d and d > 0 else 50)
    avg = sum(durs) / len(durs)
    fps = max(1, round(1000.0 / avg))
    return frames, fps, durs


def load_frames_from_webm(raw_path):
    """يفك WebM (VP9) لإطارات RGBA مع الحفاظ على الألفا."""
    info = subprocess.run([FFMPEG, "-i", raw_path],
                          capture_output=True, text=True).stderr
    m = re.search(r"(\d{2,5})x(\d{2,5})", info)
    w, h = int(m.group(1)), int(m.group(2))
    fm = re.search(r"(\d+(?:\.\d+)?) fps", info)
    fps = round(float(fm.group(1))) if fm else 12
    p = subprocess.run([FFMPEG, "-c:v", "libvpx-vp9", "-i", raw_path,
                        "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"],
                       capture_output=True)
    data = np.frombuffer(p.stdout, dtype=np.uint8)
    n = data.size // (w * h * 4)
    frames = [data[i * w * h * 4:(i + 1) * w * h * 4].reshape(h, w, 4)
              for i in range(n)]
    durs = [round(1000 / fps)] * n
    return frames, fps, durs


def pad_even(frames):
    """يضمن أبعاد زوجية (مطلوبة لبعض المرمّزات) مع خلفية شفافة."""
    h, w = frames[0].shape[:2]
    ph, pw = h + h % 2, w + w % 2
    if (ph, pw) == (h, w):
        return frames
    out = []
    for f in frames:
        canvas = np.zeros((ph, pw, 4), dtype=f.dtype)
        canvas[:h, :w] = f
        out.append(canvas)
    return out


def encode_ffmpeg(frames, fps, out_path, mode):
    """يرمّز الإطارات عبر ffmpeg حسب mode (prores/qtrle/webm)."""
    frames = pad_even(frames)
    h, w = frames[0].shape[:2]
    raw = b"".join(np.ascontiguousarray(f).tobytes() for f in frames)
    base = [FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0", "-an"]
    if mode == "prores":
        args = ["-c:v", "prores_ks", "-profile:v", "4",
                "-pix_fmt", "yuva444p10le", "-alpha_bits", "16"]
    elif mode == "qtrle":
        args = ["-c:v", "qtrle", "-pix_fmt", "argb"]
    elif mode == "webm":
        args = ["-c:v", "libvpx-vp9", "-vf", "format=yuva420p",
                "-b:v", "0", "-crf", "20", "-metadata:s:v:0", "alpha_mode=1"]
    else:
        raise ValueError(mode)
    r = subprocess.run(base + args + [out_path], input=raw, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="ignore")[-500:])


def save_gif(frames, durs, out_path):
    frames = pad_even(frames)
    imgs = [Image.fromarray(f, "RGBA") for f in frames]
    imgs[0].save(out_path, save_all=True, append_images=imgs[1:],
                 loop=0, duration=durs, disposal=2, transparency=0)


def default_name(url):
    seg = [s for s in url.split("/") if s]
    name = "_".join(seg[-2:]) if len(seg) >= 2 else (seg[-1] if seg else "download")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:60] or "download"


def process(url, fmt_key, out_dir, log):
    """العملية الكاملة: تحميل -> كشف النوع -> تحويل -> حفظ. يرجّع المسار."""
    ext, mode = FORMATS[fmt_key]
    log("⏳ جاري التحميل ...")
    data = http_get(url)
    log(f"✓ تم التحميل ({len(data)//1024} كيلوبايت)")

    name = default_name(url)
    tmp = os.path.join(out_dir, name + "_src.tmp")
    with open(tmp, "wb") as f:
        f.write(data)

    # الصيغة الأصلية: احفظ كما هو (أو PNG شفاف للصور)
    if mode == "original":
        if is_png(data):
            out = os.path.join(out_dir, name + ".png")
            Image.open(tmp).convert("RGBA").save(out)
        else:
            guess = ".webm" if is_webm(data) else ".bin"
            out = os.path.join(out_dir, name + guess)
            os.replace(tmp, out)
            log(f"✅ حُفظ: {out}")
            return out
        os.remove(tmp)
        log(f"✅ حُفظ: {out}")
        return out

    # اكتشف النوع وحمّل الإطارات
    if is_apng(data):
        log("نوع الملف: APNG متحرك")
        frames, fps, durs = load_frames_from_image(tmp)
    elif is_webm(data):
        log("نوع الملف: WebM فيديو")
        frames, fps, durs = load_frames_from_webm(tmp)
    elif is_png(data):
        log("نوع الملف: صورة PNG ثابتة")
        frames, fps, durs = load_frames_from_image(tmp)  # إطار واحد
    else:
        os.remove(tmp)
        raise RuntimeError("نوع الملف غير مدعوم للتحويل (مو APNG/WebM/PNG).")

    log(f"الإطارات: {len(frames)} | المقاس: {frames[0].shape[1]}x{frames[0].shape[0]} | fps: {fps}")

    # صورة ثابتة + صيغة فيديو => احفظها PNG بدل فيديو إطار واحد
    if len(frames) == 1 and mode in ("prores", "qtrle", "webm", "gif"):
        out = os.path.join(out_dir, name + ".png")
        Image.fromarray(frames[0], "RGBA").save(out)
        os.remove(tmp)
        log("ℹ️ الملف صورة ثابتة — حُفظ PNG شفاف بدل فيديو.")
        log(f"✅ حُفظ: {out}")
        return out

    out = os.path.join(out_dir, name + ext)
    log("⚙️ جاري التحويل ...")
    if mode == "gif":
        save_gif(frames, durs, out)
    else:
        encode_ffmpeg(frames, fps, out, mode)
    os.remove(tmp)
    log(f"✅ تم! حُفظ: {out}")
    return out


# =================== الواجهة الرسومية ===================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("محمّل ملفات ديسكورد — خلفية شفافة")
        self.geometry("640x520")
        self.configure(padx=16, pady=14)
        self.out_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self._build()

    def _build(self):
        tk.Label(self, text="محمّل ملفات ديسكورد", font=("Segoe UI", 16, "bold")).pack(anchor="e")
        tk.Label(self, text="حط الرابط، اختر الصيغة، واضغط تحميل.",
                 fg="#666").pack(anchor="e", pady=(0, 10))

        tk.Label(self, text="رابط الملف:").pack(anchor="e")
        self.url_entry = tk.Entry(self, font=("Consolas", 10))
        self.url_entry.pack(fill="x", pady=(2, 10))

        tk.Label(self, text="الصيغة:").pack(anchor="e")
        self.fmt = ttk.Combobox(self, values=list(FORMATS.keys()), state="readonly")
        self.fmt.current(0)
        self.fmt.pack(fill="x", pady=(2, 10))

        frm = tk.Frame(self)
        frm.pack(fill="x", pady=(0, 10))
        tk.Button(frm, text="📁 مجلد الحفظ", command=self.pick_dir).pack(side="right")
        self.dir_lbl = tk.Label(frm, textvariable=self.out_dir, fg="#444", anchor="w")
        self.dir_lbl.pack(side="right", fill="x", expand=True, padx=8)

        self.btn = tk.Button(self, text="⬇️  تحميل وتحويل", font=("Segoe UI", 12, "bold"),
                             bg="#5865F2", fg="white", height=2, command=self.start)
        self.btn.pack(fill="x", pady=(4, 10))

        tk.Label(self, text="السجل:").pack(anchor="e")
        self.log_box = tk.Text(self, height=11, font=("Consolas", 9), state="disabled",
                               bg="#1e1e1e", fg="#d4d4d4")
        self.log_box.pack(fill="both", expand=True)

    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.update_idletasks()

    def start(self):
        url = self.url_entry.get().strip()
        if not url.startswith("http"):
            messagebox.showwarning("تنبيه", "حط رابط صحيح يبدأ بـ http")
            return
        out_dir = self.out_dir.get()
        os.makedirs(out_dir, exist_ok=True)
        self.btn.configure(state="disabled", text="… جاري المعالجة")
        threading.Thread(target=self._worker,
                         args=(url, self.fmt.get(), out_dir), daemon=True).start()

    def _worker(self, url, fmt_key, out_dir):
        try:
            out = process(url, fmt_key, out_dir, self.log)
            self.after(0, lambda: messagebox.showinfo("تم", f"حُفظ الملف:\n{out}"))
        except Exception as e:
            self.log(f"❌ خطأ: {e}")
            self.after(0, lambda: messagebox.showerror("خطأ", str(e)))
        finally:
            self.after(0, lambda: self.btn.configure(state="normal", text="⬇️  تحميل وتحويل"))


if __name__ == "__main__":
    App().mainloop()
