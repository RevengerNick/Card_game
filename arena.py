import os

def collect_py_files(source_folder: str, output_file: str):
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for root, _, files in os.walk(source_folder):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            outfile.write(f'\n# --- {file_path} ---\n')
                            outfile.write(content)
                            outfile.write('\n\n')
                    except Exception as e:
                        print(f'Не удалось прочитать {file_path}: {e}')

# Пример использования:
# Укажи путь к папке и путь к файлу-выходу
source_dir = r'bot'
output_txt = r'output2.txt'

collect_py_files(source_dir, output_txt)