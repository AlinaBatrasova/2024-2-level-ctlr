"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument

import datetime
import json
import pathlib
import shutil
from typing import Pattern, Union

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Seed URL does not match standard pattern 'https?://(www.)?'
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
    Total number of articles is out of range from 1 to 150
    """


class IncorrectNumberOfArticlesError(Exception):
    """
    Total number of articles to parse is not integer or less than 0
    """


class IncorrectHeadersError(Exception):
    """
    Headers are not in a form of dictionary
    """


class IncorrectEncodingError(Exception):
    """
    Encoding must be specified as a string
    """


class IncorrectTimeoutError(Exception):
    """
    Timeout value must be a positive integer less than 60
    """


class IncorrectVerifyError(Exception):
    """
    Verify certificate value must either be True or False
    """

class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        self.path_to_config = path_to_config
        data = self._extract_config_content()
        self._seed_urls = data.seed_urls
        self._num_articles = data.total_articles
        self._headers = data.headers
        self._encoding = data.encoding
        self._timeout = data.timeout
        self._should_verify_certificate = data.should_verify_certificate
        self._headless_mode = data.headless_mode
        self._validate_config_content()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, encoding='utf-8') as file:
            config = json.load(file)
        return ConfigDTO(**config)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        if not isinstance(self._seed_urls, list):
            raise IncorrectSeedURLError('incorrect url')
        for url in self._seed_urls:
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                raise IncorrectSeedURLError('incorrect url')

        if not isinstance(self._num_articles, int) or self._num_articles <= 0:
            raise IncorrectNumberOfArticlesError('number is not int or less that 0')
        if self._num_articles > 150:
            raise NumberOfArticlesOutOfRangeError('wrong number of articles')
        if not isinstance(self._headers, dict):
            raise IncorrectHeadersError('incorrect type of headers')
        if not isinstance(self._encoding, str):
            raise IncorrectEncodingError('incorrect type of encoding')
        if not isinstance(self._timeout, int) or not 0 < self._timeout < 60:
            raise IncorrectTimeoutError('incorrect timeouts')
        if (not isinstance(self._should_verify_certificate, bool) or
                not isinstance(self._headless_mode, bool)):
            raise IncorrectVerifyError('type is not bool')

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self._seed_urls
    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self._num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self._headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self._encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self._timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self._should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._headless_mode

def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """
    request = requests.get(url, headers=config.get_headers(),
                           timeout=config.get_timeout(),
                           verify=config.get_verify_certificate())
    request.encoding = config.get_encoding()
    return request


class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: Union[Pattern, str]

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls = []

    def _extract_url(self, article_bs: BeautifulSoup) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.BeautifulSoup): BeautifulSoup instance

        Returns:
            str: Url from HTML
        """
        raw_href = article_bs.get('href')
        if isinstance(raw_href, list):
            raw_href = raw_href[0]
        if not isinstance(raw_href, str) or not raw_href:
            return ""
        href: str = raw_href

        if href.startswith(('http://', 'https://')):
            return href

        seed_list = self.config.get_seed_urls()
        if not seed_list:
            return ""
        base = seed_list[0]
        parts = base.split('/')
        domain = parts[0] + '//' + parts[2]
        return domain + href

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.get_search_urls():
            response = make_request(seed_url, self.config)
            if not response.ok:
                continue

            soup = BeautifulSoup(response.text, 'lxml')

            for header in soup.find_all('h3'):
                if len(self.urls) >= self.config.get_num_articles():
                    break

                a_tag = header.find('a', href=True)
                if not a_tag:
                    continue

                url = self._extract_url(a_tag)
                if url and url not in self.urls:
                    self.urls.append(url)

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


class HTMLParser:
    """
    HTMLParser implementation.
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """
        self.full_url = full_url
        self.article_id = article_id
        self.config = config
        self.article = Article(full_url, article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        body = article_soup.find("div", attrs={"itemprop": "articleBody"})
        if not isinstance(body, Tag):
            self.article.text = ""
            return
        if not body:
            self.article.text = ""

        html_field = body.find("div", attrs={"class": "field ft_html f_content auto_field"})
        if not isinstance(html_field, Tag):
            self.article.text = ""
            return
        if not html_field:
            self.article.text = ""

        value_div = html_field.find("div", attrs={"class": "value"})
        if not isinstance(value_div, Tag):
            self.article.text = ""
            return
        if not value_div:
            self.article.text = ""

        paragraphs = [
            p.get_text(strip=True)
            for p in value_div.find_all("p")
            if p.get_text(strip=True)
        ]

        self.article.text = "\n".join(paragraphs)

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        h1_tag = article_soup.find('h1')
        if h1_tag:
            headline_html = h1_tag.decode_contents().strip()
            fixed = headline_html.replace('«', '&laquo;').replace('»', '&raquo;')
            self.article.title = fixed
        else:
            self.article.title = "NOT FOUND"

        self.article.author = ['NOT FOUND']
        time_tag = article_soup.find('time')
        raw_date = time_tag.get_text(strip=True) if time_tag else ''
        self.article.date = self.unify_date_format(raw_date)
        topics = []
        about_ul = article_soup.find('ul', itemprop='about')
        if about_ul:
            for li in about_ul.find_all('li', itemprop='itemListElement'):
                meta = li.find('meta', itemprop='name')
                if meta and meta.has_attr('content'):
                    topics.append(meta['content'].strip())
        self.article.topics = topics or ['NOT FOUND']

        bc_ol = article_soup.find("ol", class_="breadcrumb")
        if bc_ol:
            crumbs: list[str] = []
            for li in bc_ol.find_all("li", itemprop="itemListElement"):
                a = li.find("a", itemprop="item")
                if isinstance(a, Tag):
                    name = a.find(attrs={"itemprop": "name"})
                    crumbs.append(name.get_text(strip=True) if name else a.get_text(strip=True))
                else:
                    name = li.find(attrs={"itemprop": "name"})
                    crumbs.append(name.get_text(strip=True) if name else '')
            self.article.map = crumbs
        else:
            self.article.map = []


    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        return datetime.datetime.strptime(date_str, "%d.%m.%Y")

    def parse(self) -> Union[Article, bool, list]:
        """
        Parse each article.

        Returns:
            Union[Article, bool, list]: Article instance
        """
        response = make_request(self.full_url, self.config)
        response.encoding = self.config.get_encoding()

        if response.ok:
            soup = BeautifulSoup(response.text, "lxml")
            self._fill_article_with_text(soup)
            self._fill_article_with_meta_information(soup)
        else:
            self.article.text = ""
        return self.article


def prepare_environment(base_path: Union[pathlib.Path, str]) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (Union[pathlib.Path, str]): Path where articles stores
    """
    if base_path.exists():
        shutil.rmtree(base_path)
    base_path.mkdir(parents=True)

def main() -> None:
    """
    Entrypoint for scrapper module.
    """
    prepare_environment(ASSETS_PATH)
    config = Config(CRAWLER_CONFIG_PATH)
    crawler = Crawler(config)
    crawler.find_articles()
    for idx, url in enumerate(crawler.urls, 1):
        parser = HTMLParser(url, idx, config)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)


if __name__ == "__main__":
    main()
