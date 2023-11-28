import os
import requests


def combine_css_files(folder_path):
    combined_css = ''
    for file in sorted(os.listdir(folder_path)):
        if file.endswith('.css') and 'min' not in file:
            print(file)
            with open(os.path.join(folder_path, file), 'r') as f:
                combined_css += f.read() + '\n'
    return combined_css


def minify_css(css_content):
    response = requests.post('https://www.toptal.com/developers/cssminifier/api/raw',
                             data={'input': css_content})
    return response.text


# Путь к папке с CSS файлами
folder_path = './static/css'

# Объединяем содержимое всех CSS файлов
combined_css = combine_css_files(folder_path)

# Сжимаем объединенный CSS
minified_css = minify_css(combined_css)

# Сохраняем сжатый CSS в файл
with open(os.path.join(folder_path, 'main.min.css'), 'w') as f:
    f.write(minified_css)
