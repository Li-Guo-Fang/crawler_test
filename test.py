import os
import multiprocessing

multiprocessing.Process

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_text(book_name, chapter):
    """ 保存正文信息 """
    text = '1234567890'
    novel_path = os.path.join(BASE_DIR, 'novel', book_name, f'{chapter}.txt')
    if not os.path.exists(novel_path):
        os.mknod(novel_path)
    # file_path = os.path.join(novel_path, f'{chapter}.txt')
    save_content_to_disk(novel_path, text)


def save_content_to_disk(path, text):
    with open(path, 'w') as fp:
        fp.write(text)


get_text('唐砖', '第一章')
