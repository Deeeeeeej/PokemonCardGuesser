import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time

class SerebiiCardScraper:
    """A specialized scraper for Serebii.net Pokemon card pages"""
    def __init__(self, set_url="https://www.serebii.net/card/journeytogether/"):
        self.set_url = set_url
        set_path = re.search(r'/card/([a-z0-9_-]+)/?', set_url, re.IGNORECASE)
        self.set_id = set_path.group(1) if set_path else None
        if not self.set_id:
            set_path = re.search(r'/card/([a-z0-9_-]+)', set_url, re.IGNORECASE)
            self.set_id = set_path.group(1) if set_path else 'journeytogether'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.output_file = "pokemon_cards.json"
        self.images_dir = "card_images"
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir)

    def scrape_card_detail(self, detail_url, set_id=None):
        print(f"Scraping card details from: {detail_url}")
        try:
            # Always use the set_id from the argument if provided, else extract from self.set_url
            if not detail_url.startswith('http'):
                if detail_url.startswith('/card/'):
                    if set_id is None:
                        set_path = re.search(r'/card/([a-z0-9_-]+)/', self.set_url, re.IGNORECASE)
                        set_id = set_path.group(1) if set_path else None
                        if not set_id:
                            set_path = re.search(r'/card/([a-z0-9_-]+)', self.set_url, re.IGNORECASE)
                            set_id = set_path.group(1) if set_path else 'journeytogether'
                    detail_url = re.sub(r'/card/([^/]+)/', f'/card/{set_id}/', detail_url)
                full_url = f"https://www.serebii.net{detail_url}"
            else:
                full_url = detail_url
            response = requests.get(full_url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            card_data = {}
            meta_img = soup.find('meta', property='og:image')
            if meta_img and meta_img.get('content'):
                card_data['image_url'] = meta_img['content']
            if 'image_url' not in card_data:
                card_image = soup.find('img', src=re.compile(r'/card/journeytogether/\d+\.(jpg|png)$'))
                if card_image and 'src' in card_image.attrs:
                    img_src = card_image['src']
                    if not img_src.startswith('http'):
                        img_src = f"https://www.serebii.net{img_src}"
                    card_data['image_url'] = img_src
            card_name_elem = soup.find('font', size='2') or soup.find('font', size='5')
            if card_name_elem:
                card_data['name'] = card_name_elem.get_text(strip=True)
            card_number_elem = soup.find(string=re.compile(r'\d+\s*/\s*\d+'))
            if card_number_elem:
                card_num_match = re.search(r'(\d+\s*/\s*\d+)', card_number_elem)
                if card_num_match:
                    card_data['number'] = card_num_match.group(1).replace(' ', '')
            # --- Improved HP extraction ---
            # Look for HP in the right-aligned font in the main card info table
            hp_val = None
            for font_tag in soup.find_all('font'):
                if font_tag.string and 'HP' in font_tag.string:
                    hp_match = re.search(r'(\d+)\s*HP', font_tag.string)
                    if hp_match:
                        hp_val = hp_match.group(1)
                        break
            if not hp_val:
                # Fallback: look for bold red font (as in <font color="#FF0000"><b>50 HP</b></font>)
                b_tags = soup.find_all('b')
                for b in b_tags:
                    if b.string and 'HP' in b.string:
                        hp_match = re.search(r'(\d+)\s*HP', b.string)
                        if hp_match:
                            hp_val = hp_match.group(1)
                            break
            if hp_val:
                card_data['hp'] = hp_val
                card_data['card_type'] = card_data.get('card_type', 'Pokémon')
            type_img = soup.find('img', src=re.compile(r'/card/image/.*\.(png|jpg)$'))
            if type_img and 'src' in type_img.attrs:
                src = type_img['src']
                type_match = re.search(r'/([^/]+)\.(png|jpg)', src)
                if type_match and type_match.group(1) not in ["common", "uncommon", "rare"]:
                    card_data['types'] = [type_match.group(1)]
                    card_data['card_type'] = f"{type_match.group(1).capitalize()} Pokémon"
            if 'card_type' not in card_data:
                card_data['card_type'] = 'Trainer'
                card_data['types'] = ['trainer']
            weakness_section = soup.find(string=re.compile(r'Weakness', re.IGNORECASE))
            if weakness_section:
                parent = weakness_section.parent
                if parent:
                    weakness_img = parent.find_next('img', src=re.compile(r'/card/image/.*\.(png|jpg)$'))
                    if weakness_img and 'src' in weakness_img.attrs:
                        src = weakness_img['src']
                        type_match = re.search(r'/([^/]+)\.(png|jpg)', src)
                        if type_match and type_match.group(1) not in ["common", "uncommon", "rare"]:
                            card_data['weakness'] = [type_match.group(1)]
            resistance_section = soup.find(string=re.compile(r'Resistance', re.IGNORECASE))
            if resistance_section:
                parent = resistance_section.parent
                if parent:
                    resistance_img = parent.find_next('img', src=re.compile(r'/card/image/.*\.(png|jpg)$'))
                    if resistance_img and 'src' in resistance_img.attrs:
                        src = resistance_img['src']
                        type_match = re.search(r'/([^/]+)\.(png|jpg)', src)
                        if type_match and type_match.group(1) not in ["common", "uncommon", "rare"]:
                            card_data['resistance'] = [type_match.group(1)]
            retreat_section = soup.find(string=re.compile(r'Retreat', re.IGNORECASE))
            if retreat_section:
                parent = retreat_section.parent
                if parent:
                    retreat_imgs = parent.find_next_siblings('img', src=re.compile(r'/card/image/colorless\.(png|jpg)$'))
                    card_data['retreat_cost'] = len(retreat_imgs) if retreat_imgs else 0
            # Capture holographic trait if present
            rarity_img = soup.find('img', src=re.compile(r'/card/image/(holographic|common|uncommon|rare|ultra|secret)\.(png|jpg)$'))
            if rarity_img and 'src' in rarity_img.attrs:
                src = rarity_img['src']
                rarity_match = re.search(r'/card/image/([a-z]+)\.(png|jpg)', src)
                if rarity_match:
                    rarity_val = rarity_match.group(1).capitalize()
                    card_data['rarity'] = rarity_val
                    # Add a boolean trait for holographic
                    if rarity_match.group(1).lower() == 'holographic':
                        card_data['holographic'] = True
                        card_data['rarity'] = 'Rare'  # Holographic is also considered Rare
                    else:
                        card_data['holographic'] = False
            if 'card_type' not in card_data:
                card_data['card_type'] = 'Trainer'
                card_data['types'] = ['trainer']
            if 'name' not in card_data:
                title = soup.title.string if soup.title else ''
                match = re.search(r'#\d+\s+(.+)', title)
                if match:
                    card_data['name'] = match.group(1).strip()
            print(f"✓ Successfully scraped details for {card_data.get('name', 'Unknown card')}")
            return card_data
        except Exception as e:
            print(f"❌ Error scraping card detail page: {e}")
            return None

    def download_image(self, image_url, card_number, card_name, set_id=None):
        try:
            if not set_id:
                set_path = re.search(r'/card/([a-z0-9_-]+)/', self.set_url, re.IGNORECASE)
                set_id = set_path.group(1) if set_path else None
                if not set_id:
                    set_path = re.search(r'/card/([a-z0-9_-]+)', self.set_url, re.IGNORECASE)
                    set_id = set_path.group(1) if set_path else 'journeytogether'
            clean_number = re.sub(r'[^\d]', '', str(card_number).split('/')[0])
            clean_name = re.sub(r'[^\x00-\x7F]+', '', str(card_name)).replace(' ', '')
            if not set_id:
                print(f"[ERROR] Could not determine set_id for image download of card {card_name}")
                return None
            images_dir = os.path.join('images', set_id)
            os.makedirs(images_dir, exist_ok=True)
            image_filename = f"{clean_number}_{clean_name}.jpg"
            image_path = os.path.join(images_dir, image_filename)
            if os.path.exists(image_path):
                print(f"✓ Already have image for {card_name}")
                return image_path
            if not image_url or not isinstance(image_url, str):
                print(f"[ERROR] No valid image_url for card {card_name}")
                return None
            if not image_url.startswith('http'):
                if image_url.startswith('/'):
                    image_url = f"https://www.serebii.net{image_url}"
                else:
                    image_url = f"https://www.serebii.net/{image_url}"
            response = requests.get(image_url, headers=self.headers)
            response.raise_for_status()
            with open(image_path, 'wb') as f:
                f.write(response.content)
            print(f"✓ Downloaded image for {card_name}")
            return image_path
        except Exception as e:
            print(f"✗ Error downloading image for {card_name}: {e}")
            return None

    def download_card_images(self, cards):
        print("\nDownloading card images for all cards...")
        set_id = self.set_id
        images_dir = os.path.join('images', set_id)
        os.makedirs(images_dir, exist_ok=True)
        # Check if any images exist for this set
        existing_images = [f for f in os.listdir(images_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if not existing_images:
            print(f"[INFO] No images found for set '{set_id}', downloading images for all cards...")
            for card in cards:
                url = card.get('image_url', '')
                num = card.get('number', '')
                name = card.get('name', '')
                local = self.download_image(url, num, name, set_id=set_id)
                card['local_image'] = local or ''
            return
        for card in cards:
            url = card.get('image_url', '')
            num = card.get('number', '')
            name = card.get('name', '')
            local = self.download_image(url, num, name, set_id=set_id)
            card['local_image'] = local or ''

    def scrape_cards(self):
        print(f"Scraping Pokemon cards from {self.set_url}")
        cards = []
        try:
            response = requests.get(self.set_url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            # Try to extract number of cards from the page text
            num_cards = None
            amount_text = soup.find(string=re.compile(r'Amount of Cards', re.IGNORECASE))
            if amount_text:
                match = re.search(r'Amount of Cards.*?(\d+)', amount_text)
                if match:
                    num_cards = int(match.group(1))
            if not num_cards:
                # Fallback: try to find in the first <p> after <h1>
                h1 = soup.find('h1')
                if h1:
                    p = h1.find_next('p')
                    if p:
                        match = re.search(r'Amount of Cards.*?(\d+)', p.get_text())
                        if match:
                            num_cards = int(match.group(1))
            print(f"[DEBUG] Detected num_cards: {num_cards}")
            # Hardcode detail page scraping if num_cards is found
            failed_at = None
            if num_cards:
                for i in range(1, num_cards+1):
                    num_str = str(i).zfill(3)
                    detail_url = f"/card/{self.set_id}/{num_str}.shtml"
                    try:
                        card_data = self.scrape_card_detail(detail_url, set_id=self.set_id)
                        if card_data and card_data.get('number'):
                            print(f"[DEBUG] Parsed card: {card_data}")
                            cards.append(card_data)
                    except Exception as e:
                        print(f"[WARN] Failed to scrape card {num_str} in set {self.set_id}: {e}")
                        failed_at = i
                        break
                # If we failed before num_cards, try H-numbering
                if failed_at and failed_at <= num_cards:
                    print(f"[INFO] Trying H-numbering for set {self.set_id} starting at H{failed_at}")
                    for h in range(failed_at, num_cards+1):
                        h_str = f"H{h}"
                        detail_url = f"/card/{self.set_id}/{h_str}.shtml"
                        try:
                            card_data = self.scrape_card_detail(detail_url, set_id=self.set_id)
                            if card_data and card_data.get('number'):
                                print(f"[DEBUG] Parsed card: {card_data}")
                                cards.append(card_data)
                        except Exception as e:
                            print(f"[WARN] Failed to scrape card {h_str} in set {self.set_id}: {e}")
            else:
                # Fallback: try to parse the table as before
                table = soup.find('table', class_='dextable')
                rows = table.find_all('tr', recursive=False)
                if len(rows) <= 1:
                    print("[DEBUG] Fallback: using all <tr> in table")
                    rows = table.find_all('tr')
                print(f"[DEBUG] Using {len(rows)} rows (including header)")
                for i, tr in enumerate(rows[:10]):
                    print(f"[DEBUG] Row {i} HTML: {tr}")
                rows = rows[1:]  # skip header
                print(f"Found {len(rows)} main-page cards to process")
                for idx, row in enumerate(rows):
                    cells = row.find_all('td')
                    print(f"[DEBUG] Row {idx} has {len(cells)} cells")
                    if len(cells) < 4:
                        print(f"[DEBUG] Skipping row {idx}: not enough cells ({len(cells)})")
                        continue
                    num_text = cells[0].get_text(strip=True)
                    print(f"[DEBUG] Row {idx} num_text: '{num_text}'")
                    match = re.search(r'(\d+)\s*/\s*\d+', num_text)
                    if not match:
                        print(f"[DEBUG] Skipping row {idx}: no card number match in '{num_text}'")
                        continue
                    number = match.group(0).replace(' ', '')
                    rarity_img = cells[0].find('img', src=re.compile(r'/card/image/.+\.png'))
                    rarity = rarity_img and re.search(r'/([^/]+)\.png', rarity_img['src']).group(1).capitalize() or 'Unknown'
                    link = cells[1].find('a')
                    if link and link.has_attr('href'):
                        detail_url = link['href']
                    else:
                        num_digits = re.search(r'(\d+)', number)
                        num_str = num_digits.group(1).zfill(3) if num_digits else '001'
                        detail_url = f"/card/{self.set_id}/{num_str}.shtml"
                    name_link = cells[2].find('a')
                    if name_link:
                        font_elem = name_link.find('font')
                        if font_elem:
                            name = font_elem.get_text(strip=True)
                        else:
                            name = name_link.get_text(strip=True)
                    else:
                        name = cells[2].get_text(strip=True)
                    detail_cell = cells[3]
                    hp = re.search(r'(\d+)HP', detail_cell.get_text())
                    hp = hp.group(1) if hp else ''
                    primary = ''
                    hp_elem = detail_cell.find(text=re.compile(r'\d+HP'))
                    if hp_elem:
                        img = hp_elem.parent.find_next('img', src=re.compile(r'/card/image/.+\.png'))
                        if img: primary = re.search(r'/([^/]+)\.png', img['src']).group(1)
                    weakness = []
                    resistance = []
                    retreat = 0
                    for hdr in detail_cell.find_all('b'):
                        txt = hdr.get_text(strip=True).lower()
                        cell = hdr.find_parent('td').find_next_sibling('td')
                        if not cell: continue
                        img = cell.find('img')
                        if txt == 'weakness' and img:
                            weakness = [re.search(r'/([^/]+)\.png', img['src']).group(1)]
                        elif txt == 'resistance' and img:
                            resistance = [re.search(r'/([^/]+)\.png', img['src']).group(1)]
                        elif txt == 'retreat cost':
                            retreat = len(cell.find_all('img', src=re.compile(r'/card/image/colorless\.png')))
                    types = [primary] if primary else []
                    card = {
                        'number': number,
                        'name': name,
                        'card_type': f"{primary.capitalize()} Pokémon" if primary else 'Unknown',
                        'types': types,
                        'rarity': rarity,
                        'hp': hp,
                        'weakness': weakness,
                        'resistance': resistance,
                        'retreat_cost': retreat,
                        'detail_url': detail_url
                    }
                    print(f"[DEBUG] Parsed card: {card}")
                    cards.append(card)
            print(f"Total cards gathered: {len(cards)}")
            self.download_card_images(cards)
            self.export_cards_to_csv(cards)
            # Save CSV to the data/ directory only (remove JSON creation)
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
            os.makedirs(data_dir, exist_ok=True)
            csv_path = os.path.join(data_dir, 'pokemon_cards_data.csv')
            # Move CSV if it was created in the current dir
            if os.path.exists('pokemon_cards_data.csv'):
                import shutil
                shutil.move('pokemon_cards_data.csv', csv_path)
            print(f"✓ Saved all {len(cards)} cards to {csv_path}")
            return cards
        except Exception as e:
            print(f"❌ scrape_cards failed: {e}")
            return []

    def export_cards_to_csv(self, cards):
        """Export card data to CSV for easy inspection"""
        csv_file = "pokemon_cards_data.csv"
        try:
            import csv
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Header row
                writer.writerow(["Number", "Name", "Card Type", "Types", "Rarity", "HP", "Weakness", "Resistance", "Retreat Cost", "Image URL", "Local Image"])
                # Write card rows
                for card in cards:
                    writer.writerow([
                        card.get('number', ''),
                        card.get('name', ''),
                        card.get('card_type', ''),
                        ";".join(card.get('types', [])),
                        card.get('rarity', ''),
                        card.get('hp', ''),
                        ";".join(card.get('weakness', [])),
                        ";".join(card.get('resistance', [])),
                        card.get('retreat_cost', 0),
                        card.get('image_url', ''),
                        card.get('local_image', '')
                    ])
            print(f"✓ Exported card data to {csv_file}")
        except Exception as e:
            print(f"✗ Error exporting cards to CSV: {e}")

    def scrape_cards_to_csv(self, csv_path):
        # Scrape cards for the current set_url and write to the given csv_path
        cards = self.scrape_cards()
        if not cards:
            print(f"[ERROR] No cards scraped for set: {self.set_url}")
            return []
        import csv
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Number", "Name", "Card Type", "Types", "Rarity", "HP", "Weakness", "Resistance", "Retreat Cost", "Image URL", "Local Image"])
            for card in cards:
                writer.writerow([
                    card.get('number', ''),
                    card.get('name', ''),
                    card.get('card_type', ''),
                    ";".join(card.get('types', [])),
                    card.get('rarity', ''),
                    card.get('hp', ''),
                    ";".join(card.get('weakness', [])),
                    ";".join(card.get('resistance', [])),
                    card.get('retreat_cost', 0),
                    card.get('image_url', ''),
                    card.get('local_image', '')
                ])
        print(f"[INFO] Scraped and saved {len(cards)} cards to {csv_path}")
        return cards

if __name__ == "__main__":
    print("[INFO] Running SerebiiCardScraper as a script...")
    scraper = SerebiiCardScraper()
    scraper.scrape_cards()
    print("[INFO] Scraping complete.")
