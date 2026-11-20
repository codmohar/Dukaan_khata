import zlib
import struct
import math
from pathlib import Path

def create_png(width, height, output_path):
    # Generates a crisp emerald green icon with rounded rectangle and store/microphone motif
    raw_data = bytearray()
    
    cx, cy = width / 2.0, height / 2.0
    radius = width * 0.45
    corner_radius = width * 0.22
    
    for y in range(height):
        raw_data.append(0) # Filter type 0 (None)
        for x in range(width):
            # Check rounded box distance
            dx = max(abs(x - cx) - (cx - corner_radius), 0)
            dy = max(abs(y - cy) - (cy - corner_radius), 0)
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist > corner_radius:
                # Transparent outside rounded squircle
                raw_data.extend([0, 0, 0, 0])
            else:
                # Background gradient: Emerald 600 (#059669) to Emerald 800 (#065f46)
                t = (x + y) / (width + height)
                r = int(5 * (1 - t) + 6 * t)
                g = int(150 * (1 - t) + 95 * t)
                b = int(105 * (1 - t) + 70 * t)
                
                # Draw white shopping bag / ledger book shape in center
                nx = (x - cx) / width
                ny = (y - cy) / height
                
                # Check if inside central icon
                # A stylish store khata book with rupee / mic symbol
                in_book = (-0.22 <= nx <= 0.22) and (-0.26 <= ny <= 0.26)
                spine = (-0.02 <= nx <= 0.02) and (-0.26 <= ny <= 0.26)
                lines = (abs(nx) > 0.06 and abs(nx) < 0.18) and (
                    abs(ny + 0.12) < 0.02 or abs(ny + 0.02) < 0.02 or abs(ny - 0.08) < 0.02
                )
                
                if in_book and not spine and not lines:
                    raw_data.extend([255, 255, 255, 255])
                else:
                    raw_data.extend([r, g, b, 255])
                    
    # PNG format structure
    def chunk(tag, data):
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xffffffff)
        
    ihdr = struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0)
    compressed = zlib.compress(bytes(raw_data), 9)
    
    png_bytes = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
    
    Path(output_path).write_bytes(png_bytes)
    print(f"Generated {output_path} ({len(png_bytes)} bytes)")

pub_dir = Path(r"c:\Users\466mo\OneDrive\Desktop\beng_ai_ver\Dukkan\dukaan-ai\web\public")
create_png(192, 192, pub_dir / "icon-192.png")
create_png(512, 512, pub_dir / "icon-512.png")
create_png(192, 192, pub_dir / "apple-touch-icon.png")

# Also for mobile assets
mobile_assets = Path(r"c:\Users\466mo\OneDrive\Desktop\beng_ai_ver\Dukkan\dukaan-ai\mobile\assets")
create_png(192, 192, mobile_assets / "icon.png")
create_png(512, 512, mobile_assets / "adaptive-icon.png")
create_png(512, 512, mobile_assets / "splash.png")

