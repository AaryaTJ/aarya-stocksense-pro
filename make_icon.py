"""
Processes user-provided brand assets into all required formats:
  aarya_stocksense_icon.png  → aarya_icon.ico  (multi-size, taskbar / .exe)
                             → aarya_icon.png  (256px, browser favicon)
  aarya_stocksense_logo.png  → aarya_logo_sidebar.png  (cropped, sidebar header)
"""
from PIL import Image
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# ── 1. TASKBAR / EXE ICON ─────────────────────────────────────────────
def remove_white_bg(img: Image.Image) -> Image.Image:
    """Make near-white pixels transparent."""
    img = img.convert("RGBA")
    data = np.array(img)
    r, g, b, a = data[...,0], data[...,1], data[...,2], data[...,3]
    mask = (r > 230) & (g > 230) & (b > 230)
    data[mask, 3] = 0
    return Image.fromarray(data)

def composite_on_navy(img: Image.Image, size: int) -> Image.Image:
    """Resize RGBA image onto a solid navy RGB canvas."""
    resized = img.resize((size, size), Image.LANCZOS)
    bg = Image.new("RGB", (size, size), (15, 27, 45))
    bg.paste(resized, mask=resized.split()[3])
    return bg

src_icon = Image.open(os.path.join(BASE, "aarya_stocksense_icon.png"))
icon_rgba = remove_white_bg(src_icon)

sizes    = [256, 128, 64, 48, 32, 16]
ico_imgs = [composite_on_navy(icon_rgba, s) for s in sizes]

ico_path = os.path.join(BASE, "aarya_icon.ico")
ico_imgs[0].save(ico_path, format="ICO", append_images=ico_imgs[1:])
print(f"OK ICO:     {ico_path}")

# favicon PNG — transparent rounded icon for browser tab
png_path = os.path.join(BASE, "aarya_icon.png")
icon_rgba.resize((256, 256), Image.LANCZOS).save(png_path, format="PNG")
print(f"OK Favicon saved: {png_path}")

# ── 2. SIDEBAR LOGO ───────────────────────────────────────────────────
src_logo = Image.open(os.path.join(BASE, "aarya_stocksense_logo.png")).convert("RGB")
arr      = np.array(src_logo)

# Find bounding box of non-black content (brightness > 15)
bright = arr.max(axis=2)
rows   = np.any(bright > 15, axis=1)
cols   = np.any(bright > 15, axis=0)

if rows.any() and cols.any():
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    pad  = int(min(rmax - rmin, cmax - cmin) * 0.06)   # 6% padding
    rmin = max(0, rmin - pad);  rmax = min(src_logo.height - 1, rmax + pad)
    cmin = max(0, cmin - pad);  cmax = min(src_logo.width  - 1, cmax + pad)
    cropped = src_logo.crop((cmin, rmin, cmax + 1, rmax + 1))
else:
    cropped = src_logo

sidebar_path = os.path.join(BASE, "aarya_logo_sidebar.png")
cropped.save(sidebar_path, format="PNG")
print(f"OK Sidebar logo:  {sidebar_path}  ({cropped.width}×{cropped.height}px)")
