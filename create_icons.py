from PIL import Image, ImageDraw

def create_icon(size):
    # Создаем новое изображение с белым фоном
    image = Image.new('RGB', (size, size), 'white')
    draw = ImageDraw.Draw(image)
    
    # Рисуем круг
    margin = size // 8
    draw.ellipse([margin, margin, size-margin, size-margin], fill='#4CAF50')
    
    # Рисуем стрелку вниз
    arrow_width = size // 4
    arrow_height = size // 3
    x1 = size // 2 - arrow_width // 2
    y1 = size // 2 - arrow_height // 2
    x2 = size // 2 + arrow_width // 2
    y2 = size // 2 + arrow_height // 2
    draw.polygon([(x1, y1), (x2, y1), (size//2, y2)], fill='white')
    
    return image

# Создаем иконки разных размеров
for size in [48, 128]:
    icon = create_icon(size)
    icon.save(f'browser_extension/icon{size}.png') 