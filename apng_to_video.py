from PIL import Image, ImageSequence
import imageio.v2 as imageio
import numpy as np

src = "collectible_animated"
im = Image.open(src)
n = getattr(im, "n_frames", 1)
print("frames:", n)

# جمع الفريمات + المدة
frames = []
durations = []
for frame in ImageSequence.Iterator(im):
    rgba = frame.convert("RGBA")
    # خلفية بيضاء للأجزاء الشفافة (الفيديو ما يدعم الشفافية)
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    bg.alpha_composite(rgba)
    frames.append(np.array(bg.convert("RGB")))
    d = frame.info.get("duration", 50)  # ms
    durations.append(d if d and d > 0 else 50)

avg_ms = sum(durations) / len(durations)
fps = max(1, round(1000.0 / avg_ms))
print("avg frame ms:", round(avg_ms, 1), "-> fps:", fps)

# تأكد الأبعاد زوجية (مطلوب لـ yuv420p/H.264)
h, w, _ = frames[0].shape
def pad_even(a):
    ph = a.shape[0] + (a.shape[0] % 2)
    pw = a.shape[1] + (a.shape[1] % 2)
    if (ph, pw) != (a.shape[0], a.shape[1]):
        out = np.full((ph, pw, 3), 255, dtype=a.dtype)
        out[:a.shape[0], :a.shape[1]] = a
        return out
    return a
frames = [pad_even(f) for f in frames]

# MP4 (H.264)
imageio.mimwrite("collectible.mp4", frames, fps=fps, codec="libx264",
                 quality=8, macro_block_size=1,
                 ffmpeg_params=["-pix_fmt", "yuv420p"])
print("wrote collectible.mp4")

# WebM (VP9)
imageio.mimwrite("collectible.webm", frames, fps=fps, codec="libvpx-vp9", quality=8)
print("wrote collectible.webm")
