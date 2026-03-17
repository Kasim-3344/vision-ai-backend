import sys
import cv2
import numpy as np
import os
import logging
import urllib.request
import torch
from torch import nn
from PIL import Image

# 1. MUTE ALL SYSTEM LOGS
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3" 
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
logging.getLogger("transformers").setLevel(logging.ERROR)
import warnings
warnings.filterwarnings("ignore")

old_stderr = sys.stderr
sys.stderr = open(os.devnull, 'w')
from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation
sys.stderr = old_stderr

def get_real_texture(tile_name, backend_dir):
    """Fetches the floor texture from your URLs."""
    urls = {
        "Acton": "https://www.wonderfloor.co.in/wd_admin/shades_images/37214658552107.jpg",
        "Holmes": "https://www.wonderfloor.co.in/wd_admin/shades_images/96584713552114.jpg",
        "Cedar": "https://www.wonderfloor.co.in/wd_admin/shades_images/16983742554306.jpg",
        "Faye": "https://www.wonderfloor.co.in/wd_admin/shades_images/36812945557304.jpg",
        "Calla": "https://www.wonderfloor.co.in/wd_admin/shades_images/64158972557305.jpg",
        "Tansy": "https://www.wonderfloor.co.in/wd_admin/shades_images/21458679557306.jpg",
        "Poppy1": "https://www.wonderfloor.co.in/wd_admin/shades_images/34527196557701.jpg"
    }
    url = urls.get(tile_name, urls["Holmes"])
    tex_path = os.path.join(backend_dir, f"cache_{tile_name}.jpg")
    
    if not os.path.exists(tex_path):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(tex_path, 'wb') as out_file:
                out_file.write(response.read())
        except: pass 

    tex = cv2.imread(tex_path)
    return cv2.resize(tex, (450, 450)) if tex is not None else np.full((300,300,3), 180, np.uint8)

def process_room(image_path, tile_name):
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    img = cv2.imread(image_path)
    if img is None: sys.exit(1)
        
    # Resize for stability
    h, w = img.shape[:2]
    if max(h, w) > 1024:
        scale = 1024 / max(h, w)
        img = cv2.resize(img, (int(w*scale), int(h*scale)))
        h, w = img.shape[:2]

    # 2. AI SEGMENTATION (NATIVE TOP PREDICTION)
    model_name = "nvidia/segformer-b5-finetuned-ade-640-640"
    processor = SegformerImageProcessor.from_pretrained(model_name)
    model = SegformerForSemanticSegmentation.from_pretrained(model_name)
    inputs = processor(images=Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), return_tensors="pt")
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    logits = nn.functional.interpolate(outputs.logits, size=(h, w), mode="bilinear", align_corners=False)
    
    # Get the absolute #1 most confident class for every pixel
    predicted_classes = logits.argmax(dim=1)[0].numpy()
    
    # 3 = Floor, 29 = Rug. This naturally ignores walls, tables, and cabinets.
    mask = np.isin(predicted_classes, [3, 29]).astype(np.uint8) * 255

    # 3. PREMIUM MASK TWEAKS
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    
    mask_blur = cv2.GaussianBlur(mask, (5, 5), 0)
    alpha = np.expand_dims(mask_blur.astype(np.float32) / 255.0, axis=2)

    # 4. PERSPECTIVE TEXTURE
    tex = get_real_texture(tile_name, backend_dir)
    tiled = np.tile(tex, (int(h/60)+4, int(w/60)+4, 1))[:h*4, :w*4]
    pts1 = np.array([[0, h*4], [w*4, h*4], [w*4, 0], [0, 0]], dtype=np.float32)
    pts2 = np.array([[-w*1.5, h*1.4], [w*2.5, h*1.4], [w*0.8, -h*0.1], [w*0.2, -h*0.1]], dtype=np.float32)
    warped = cv2.warpPerspective(tiled, cv2.getPerspectiveTransform(pts1, pts2), (w, h)).astype(np.float32)

    # 5. SHADOWS
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dist_transform = np.clip(cv2.distanceTransform(mask, cv2.DIST_L2, 5)/45.0, 0.7, 1.0)
    base_shadows = np.clip(gray.astype(np.float32)/185.0, 0.3, 1.0)
    shadows = np.expand_dims(base_shadows * dist_transform, axis=2)
    
    final_floor = (warped * 0.88) * shadows

    # 6. SAVE OUTPUTS TO UPLOADS FOLDER (FAST STATIC ONLY)
    target_dir = os.path.dirname(image_path)
    
    img_f = img.astype(np.float32)
    res_img = (final_floor * alpha) + (img_f * (1.0 - alpha))
    res_u8 = np.clip(res_img, 0, 255).astype(np.uint8)
    
    # Save Static Image
    img_name = f"premium_{os.path.basename(image_path)}"
    cv2.imwrite(os.path.join(target_dir, img_name), res_u8)

    # 7. OUTPUT ONLY FILENAME
    print(img_name, flush=True)
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) > 2:
        process_room(sys.argv[1], sys.argv[2])