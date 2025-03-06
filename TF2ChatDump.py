import sys
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from colorama import Fore, Back, Style, init
import re
import argparse

LOG_TF_URL = 'https://logs.tf'

solo_mode = 0

# Print console and file together
class DualWriter:
    def __init__(self, file):
        self.file = file
    
    def write(self, message):
        # File
        colourless_message = re.sub(r'\033\[[0-9;]*m', '', message)
        self.file.write(colourless_message)
        
        # Console
        sys.__stdout__.write(message)

    def flush(self):
        pass

async def fetch_html(session, url):
    async with session.get(url) as response:
        if response.status == 429:  # "Too Many Requests"
            await asyncio.sleep(1)
            return await fetch_html(session, url)  # Recursively call to retry the request
        return await response.text()

# Process logs
async def process_log(session, steam_id, log_url, alias, dual_writer):
    log_html = await fetch_html(session, log_url)
    log_soup = BeautifulSoup(log_html, 'html.parser')

    # Find the date span and set default if not found
    date_span = log_soup.find('span', class_='datefield')
    if date_span:
        date = date_span.text.strip()  # strip removes any leading/trailing whitespace

    # Find the entry for the specific player

    player = log_soup.find('tr')
    searched_player = log_soup.find('tr', id='player_' + steam_id)
    chat_names = []

    if player:
        alias = searched_player.find('a', class_='dropdown-toggle').text

        if solo_mode:
            chat_names = log_soup.find_all('td', class_='chat-name', string=alias)
        else:
            chat_names = log_soup.find_all('td', class_='chat-name')

        # Check if chat entries are found
        if chat_names:
            dual_writer.write('=' * 63 + '\n')
            dual_writer.write(f"{Fore.YELLOW}{log_url}: {Fore.CYAN}{date}\n")

            for name in chat_names:
                row = name.find_parent('tr')
                if row:
                    team = row.find_all('td')[0].text.strip()
                    username = row.find_all('td')[1].text.strip()
                    message = row.find_all('td')[2].text.strip()

                    colour = Style.RESET_ALL
                    highlight = ""

                    if not solo_mode:
                        if alias == username:
                            highlight = Back.YELLOW
                        if (team == 'Red'):
                            colour = Fore.RED
                        if (team == 'Blu'):
                            colour = Fore.BLUE                

                        print(f"{colour}{highlight}{username}{Style.RESET_ALL}: {message}   ")
                        
                        if alias == username:
                            dual_writer.file.write(f"[**** {username}: {message} ****]\n")
                        else:
                            dual_writer.file.write(f"{username}: {message}\n")
                    else:
                        dual_writer.write(f"{colour}{highlight}{username}{Style.RESET_ALL}: {message}\n")

            dual_writer.write('\n')

# Process the player's profile and fetch logs
async def process_profile(session, profile_url, dual_writer):
    profile_html = await fetch_html(session, profile_url)
    profile_soup = BeautifulSoup(profile_html, 'html.parser')

    # Get last page of logs
    pagination = profile_soup.find('div', class_='pagination')
    if pagination is None:
        print("Invalid log.tf profile URL")
        exit(1)
    pages = pagination.find_all('li')
    last_page = int(pages[-2].text.strip())

    for page_num in range(1, last_page):
        page_url = f"{profile_url}?p={page_num}"
        page_html = await fetch_html(session, page_url)
        page_soup = BeautifulSoup(page_html, 'html.parser')

        log_entries = page_soup.find_all('td')

        processed_logs = set()  # Avoid duplicate logs
        tasks = []  # Async tasks

        for log_entry in log_entries:
            entry_url = log_entry.find('a')

            if entry_url and 'href' in entry_url.attrs:
                log_url = entry_url['href']

                if log_url.startswith('/'):
                    log_url = LOG_TF_URL + log_url

                if log_url not in processed_logs:
                    processed_logs.add(log_url)

                    tasks.append(process_log(session, profile_url.split('/')[-1], log_url, entry_url.text.strip(), dual_writer))

        # Run the tasks concurrently for logs
        await asyncio.gather(*tasks)

        # Increment page number for the next iteration
        page_num += 1

def main():
    init(autoreset=True)

    parser = argparse.ArgumentParser(description="Search every message ever sent from players in games a played by specified player on games captured by logs.tf")

    parser.add_argument('URL', help='logs.tf profile URL (e.g. \'https://logs.tf/profile/76561198206875340\')', type=str)
    parser.add_argument('-s', '--solo', help='solo  mode (only display messages send by the specified player)', action='store_true')

    args = parser.parse_args();
    profile_url = args.URL

    pattern = re.compile(r'https://logs\.tf/profile/\d{17}$')
    if not pattern.match(profile_url):
        parser.print_usage()
        return(1)

    if args.solo:
        global solo_mode
        solo_mode = 1
    
    steam_number = profile_url.split('/')[-1]
    filename = steam_number+'_chat_logs.txt'
    if solo_mode:
        filename = steam_number+'_solo_chat_logs.txt'
    
    with open(filename, 'a', encoding='utf-8') as file:
        dual_writer = DualWriter(file)

        # Event loop
        asyncio.run(main_async(profile_url, dual_writer))

async def main_async(profile_url, dual_writer):
    async with aiohttp.ClientSession() as session:
        await process_profile(session, profile_url, dual_writer)

if __name__ == "__main__":
    main()