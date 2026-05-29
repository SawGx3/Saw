"""يحوّل ملف APNG (مثل collectibles ديسكورد) إلى فيديو.
- WebM (VP9) مع خلفية شفافة (قناة ألفا)
- GIF شفاف كخيار احتياطي
"""
from PIL import Image, ImageSequence
import numpy as np
import subprocess, shutil, os

src = "collectible_animated"
im = Image.open(src)
n = getattr(im, "n_frames", 1)
print("frames:", n)

frames = []
durations = []
for frame in ImageSequence.Iterator(im):
    frames.append(np.array(frame.convert("RGBA")))
    d = frame.info.get("duration", 50)
    durations.append(d if d and d > 0 else 50)

avg_ms = sum(durations) / len(durations)
fps = max(1, round(1000.0 / avg_ms))
print("fps:", fps)

# أبعاد زوجية مطلوبة للترميز
h, w, _ = frames[0].shape
def pad_even(a):
    ph, pw = a.shape[0] + a.shape[0] % 2, a.shape[1] + a.shape[1] % 2
    if (ph, pw) != a.shape[:2]:
        out = np.zeros((ph, pw, 4), dtype=a.dtype)  # شفاف
        out[:a.shape[0], :a.shape[1]] = a
        return out
    return a
frames = [pad_even(f) for f in frames]
h, w, _ = frames[0].shape

# --- WebM شفاف عبر ffmpeg (yuva420p) ---
import imageio_ffmpeg
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
raw = b"".join(f.tobytes() for f in frames)
cmd = [ffmpeg, "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
       "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0",
       "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
       "-b:v", "0", "-crf", "20", "-an", "collectible_transparent.webm"]
subprocess.run(cmd, input=raw, check=True, capture_output=True)
print("wrote collectible_transparent.webm")

# --- GIF شفاف ---
pil_frames = [Image.fromarray(f, "RGBA") for f in frames]
pil_frames[0].save("collectible_transparent.gif", save_all=True,
                   append_images=pil_frames[1:], loop=0,
                   duration=durations, disposal=2, transparency=0)
print("wrote collectible_transparent.gif")
