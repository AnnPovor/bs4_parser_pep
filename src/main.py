import logging
import re
from collections import defaultdict
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging, logger
from constants import BASE_DIR, EXPECTED_STATUS, MAIN_DOC_URL, PEP_URL, RESULTS
from outputs import control_output
from utils import find_tag, get_response


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')

    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})

    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})

    sections_by_python = div_with_ul.find_all('li',
                                              attrs={'class': 'toctree-l1'})

    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, 'lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        RESULTS.append(
            (version_link, h1.text, dl_text)
        )

        return RESULTS


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')
    sidebar = find_tag(soup, 'div', {'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Не найден список c версиями Python')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')

    main_tag = find_tag(soup, 'div', {'role': 'main'})
    table_tag = find_tag(main_tag, 'table', {'class': 'docutils'})
    pdf_a4_tag = find_tag(table_tag, 'a',
                          {'href': re.compile(r'.+pdf-a4\.zip$')})
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)

    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response = session.get(archive_url)
    with open(archive_path, 'wb') as file:
        file.write(response.content)
    logger.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    response = session.get(PEP_URL)
    response.encoding = 'utf-8'

    soup = BeautifulSoup(response.text, features='lxml')
    main_section = find_tag(soup, 'section', attrs={'id': 'numerical-index'})
    section_with_tr = main_section.find_all('tr')

    count_status_in_card = defaultdict(int)
    results = [('Статус', 'Количество')]

    for i in tqdm(range(1, len(section_with_tr))):
        href = section_with_tr[i].a['href']
        version_link = urljoin(PEP_URL, href)
        response = session.get(version_link)
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'lxml')
        card_tag = find_tag(soup, 'section', attrs={'id': 'pep-content'})
        information_tag = find_tag(
            card_tag, 'dl', attrs={'class': 'rfc2822 field-list simple'})
        for status_tag in information_tag:
            if 'Status' in status_tag:
                status = status_tag.next_sibling.next_sibling.string
                count_status_in_card[status] += 1

        total = len(section_with_tr) - 1
    abbr = main_section.find_all('abbr')
    for preview in abbr:
        preview_status = preview.text[1:]
        if status[0] != preview_status:
            logging.info(
                '\n'
                'Несовпадающие статусы:\n'
                f'{version_link}\n'
                f'Статус в карточке: {status}\n'
                f'Ожидаемые статусы: '
                f'{EXPECTED_STATUS[preview_status]}\n'
            )

    for key in count_status_in_card:
        results.append((key, str(count_status_in_card[key])))
    results.append(('Total:', total))
    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')
    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()
    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
