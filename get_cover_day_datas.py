import re
import os
import sqlite3
from enum import Enum
from collections import namedtuple
import requests
from bs4 import BeautifulSoup as bs

TIMEOUT = 10
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class CrawlStatus(Enum):
    UNUSED = 0
    USED = 1
    FINISHED = 2
    FAIL = 3


class SqlHandler:
    def __init__(self, db_path):
        self.connect = sqlite3.connect(db_path)

    def __del__(self):
        self.connect.close()

    def sql_executemany(self, sql, data):
        cursor = self.connect.cursor()
        cursor.executemany(sql, data)
        self.connect.commit()
        cursor.close()

    def sql_execute(self, sql):
        cursor = self.connect.cursor()
        cursor.execute(sql)
        self.connect.commit()
        cursor.close()

    def sql_query(self, sql):
        cur = self.connect.execute(sql)
        data = cur.fetchall()
        return data


class GetInfoBase:
    BASE_URL = 'http://www.tstdoors.com'
    DB_PATH = './books_manage.db'

    def __init__(self):
        self.sql_handler = SqlHandler(self.DB_PATH)

    @staticmethod
    def get_html_text(url):
        """ 获取url对应html页面信息
        :param url: 网址信息
        :return: response.text 网页响应文本
        """

        header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36',
            'host': 'www.tstdoors.com'
        }
        response = requests.get(url, headers=header, timeout=TIMEOUT)
        if response.status_code == 200:
            return response.text
        raise Exception(f"网页连接失败:{response.status_code}")

    def get_book_info_id(self, book_name):
        # 查询 book_id
        sql = f'SELECT BOOK_ID FROM BOOK_INFO WHERE NAME="{book_name}"'
        return self.sql_handler.sql_query(sql)[0][0]


class GetCatalogueInfo(GetInfoBase):
    def parse_html(self, html):
        """ 解析章节名称和url """
        chapter_list = []
        obj = bs(html, 'html.parser')
        pic_info = obj.select('ul[class="section-list fix"]')[1]
        pattern1 = re.compile('<li><a href="(.*?)".*?>(.*?)</a></li>')
        result = re.findall(pattern1, str(pic_info))
        for href, chapter in result:
            chapter_url = namedtuple('chapter_url', ['chapter', 'url'])
            chapter_list.append(chapter_url(chapter=chapter, url=self.BASE_URL + href))
        return chapter_list

    @staticmethod
    def get_book_info(html):
        """ 解析书详细信息 """
        obj = bs(html, 'html.parser')
        node = obj.select('div[class="info"]')

        name_pattern = re.compile('<h1>(.*?)</h1>')
        author_pattern = re.compile('<p>作者：(.*?)</p>')
        type_pattern = re.compile('<p class="xs-show">类别：(.*?)</p>')
        status_pattern = re.compile('<p class="xs-show">状态：(.*?)</p>')

        name = re.findall(name_pattern, str(node))[0]
        author = re.findall(author_pattern, str(node))[0]
        book_type = re.findall(type_pattern, str(node))[0]
        status = re.findall(status_pattern, str(node))[0]

        book_info = namedtuple('book_info', ['name', 'author', 'book_type', 'status'])
        return book_info(name=name, author=author, book_type=book_type, status=status)

    @staticmethod
    def get_catalogue_url(html_text):
        """ 解析下一页目录url """
        pattern = re.compile('<a href="(.*?)" class="onclick">下一页</a>')
        res = re.search(pattern, html_text)
        if res:
            url = GetCatalogueInfo.BASE_URL + res.group(1)
            return url
        return None

    def save_book_info(self, data, book_id):
        """ 保存书详细信息到数据库 """
        data_values = (book_id,) + tuple(data)
        sql = f'INSERT OR IGNORE INTO BOOK_INFO (BOOK_ID,NAME,AUTHOR,BOOK_TYPE,STATUS) VALUES {data_values}'
        text_sql = f"""
                    CREATE TABLE IF NOT EXISTS "context_{book_id}" (
                    `id`                INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                    `BOOK_NAME`	        VARCHAR(50) NOT NULL,
                    `CHAPTER_NAME`	    VARCHAR(200) NOT NULL UNIQUE,
                    `CONTEXT`	        TEXT NOT NULL,
                    `CREATETIME`	    DATETIME,
                    `UPDATATIME`	    DATETIME
                    );
        """
        self.sql_handler.sql_execute(sql)
        self.sql_handler.sql_execute(text_sql)

    def parse_book_id(self, url):
        pattern = re.compile('/ldks/(\d+)/')
        return re.search(pattern, url).group(1)

    def save_data(self, book_info, book_id, catalogue_list):
        # 1.保存书数据信息到数据库
        # 2.创建目录表
        # 3.保存目录信息到目录表
        self.save_book_info(book_info, book_id)
        catalogue_sql = f"""
                                CREATE TABLE IF NOT EXISTS "catalogue_{book_id}" (
                                    `BOOK_NAME`	    VARCHAR(50) NOT NULL,
                                    `URL`	        VARCHAR(100) NOT NULL UNIQUE,
                                    `CHAPTER`	    VARCHAR(50),
                                    `STATUS`	    INT,
                                    `CREATETIME`	DATETIME,
                                    `UPDATATIME`	DATETIME,
                                    `id`	        INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE
                                );
                """
        self.sql_handler.sql_execute(catalogue_sql)
        catalogue_base_sql = f'INSERT OR IGNORE INTO catalogue_{book_id} (BOOK_NAME,CHAPTER,URL,STATUS) VALUES (?,?,?,?)'
        self.sql_handler.sql_executemany(catalogue_base_sql, catalogue_list)

    def get_data_process(self, catalogue_url):
        """
        获取目录详细信息
        :param catalogue_url: 目录首页url
        :return: 书信息、目录列表
        """
        catalogue_list = []
        book_info = {}
        while catalogue_url is not None:
            html_text = self.get_html_text(catalogue_url)
            book_info = self.get_book_info(html_text)
            catalogue_info = self.parse_html(html_text)
            next_catalogue_url = self.get_catalogue_url(html_text)

            book_name = book_info.name
            for catalogue in catalogue_info:
                catalogue_list.append(
                    (book_name, catalogue.chapter, catalogue.url, CrawlStatus.UNUSED.value))
            print(f'\r已获取《{book_name}》目录数量：', len(catalogue_list), end='', flush=True)
            catalogue_url = next_catalogue_url
        return book_info, catalogue_list

    def main(self, catalogue_url):
        book_id = self.parse_book_id(catalogue_url)

        book_info, catalogue_list = self.get_data_process(catalogue_url)
        self.save_data(book_info, book_id, catalogue_list)


class GetArticleInfo(GetInfoBase):

    @staticmethod
    def get_next_page_url(html_text):
        pattern = re.compile('<a href="(.*?)">下一页</a>')
        res = re.search(pattern, html_text)
        if res:
            url = GetCatalogueInfo.BASE_URL + res.group(1)
            return url
        return None

    @staticmethod
    def parse_html(html):
        """ 解析正文 """
        obj = bs(html, 'html.parser')
        node_info = obj.select('div[id="content"]')[0]
        pattern = re.compile('</div>(.*)<div.*?</div><br/>(.*)<br/>', re.S | re.M)
        result = re.findall(pattern, str(node_info))
        result = [[j.strip() for j in i] for i in result]
        text = ''.join([''.join(x) for x in result]).replace('<br/>　　<br/>　　', '\n').replace('<br/>', '\n').replace(
            '\u3000', '').replace('\\', '').replace(' ', '').replace('"', '“').strip()
        return text

    def get_context(self, url):
        """ 获取每章全部正文 """
        text = ''
        while url:
            html_text = self.get_html_text(url)
            text += self.parse_html(html_text)
            next_url = GetArticleInfo.get_next_page_url(html_text)
            url = next_url
        return text

    def save_context_info(self, data):
        sql = f'INSERT OR IGNORE INTO context_info (BOOK_ID,BOOK_NAME,CHAPTER_NAME,CONTEXT_PATH) VALUES {data}'
        self.sql_handler.sql_execute(sql)

    def get_chapter_url_list(self, book_id, book_name):
        """ 查询章节url """
        sql = f'select BOOK_NAME,CHAPTER,URL from CATALOGUE_{book_id} where status != "{CrawlStatus.USED.value}" and BOOK_NAME="{book_name}"'
        return self.sql_handler.sql_query(sql)

    def get_text(self, book_id, book_name, chapter, url):
        """ 保存正文信息 """
        chapter = chapter.replace('?', '')
        text = self.get_context(url)
        novel_path = os.path.join(BASE_DIR, 'novel', book_name)
        if not os.path.exists(novel_path):
            os.makedirs(novel_path)
        file_path = os.path.join(novel_path, f'{chapter}.txt')
        self.save_content_to_disk(file_path, text)

        data = (book_id, book_name, chapter, file_path)
        self.save_context_info(data)

    def save_content_to_disk(self, path, text):
        with open(path, 'w') as fp:
            fp.write(text)

    def main(self, book_name):
        book_id = self.get_book_info_id(book_name)
        chapter_info_list = self.get_chapter_url_list(book_id, book_name)
        for name, chapter, url in chapter_info_list:
            self.get_text(book_id, name, chapter, url)
            sql = f'update catalogue_{book_id} set status="{CrawlStatus.USED.value}" where url="{url}"'
            self.sql_handler.sql_execute(sql)
            print(f"""\r小说名称:《{name}》 章节：{chapter}  url: {url}""", end='', flush=True)


if __name__ == '__main__':
    while True:
        try:
            first_url = 'http://www.tstdoors.com/ldks/6114/'
            GetCatalogueInfo().main(first_url)
            GetArticleInfo().main("天才相师")
        except Exception as e:
            print(e)
