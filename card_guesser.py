import sys
import os
import csv
import random
import requests
import pandas as pd
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QGridLayout, QScrollArea, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QMessageBox, QInputDialog, QListWidget, QListWidgetItem, QFrame, QDialog, QProgressBar, QSizePolicy, QComboBox
)
from PyQt6.QtGui import QPixmap, QFont, QIcon
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer
from scraper.serebii_card_scraper import SerebiiCardScraper
import secrets
import string
import socket
import threading
import json
import base64
import hashlib
from cryptography.fernet import Fernet

def generate_shared_key(session_code):
    # Derive a 32-byte key from the session code using SHA-256
    digest = hashlib.sha256(session_code.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)

def encrypt_message(message, session_code):
    key = generate_shared_key(session_code)
    f = Fernet(key)
    token = f.encrypt(message.encode('utf-8'))
    return token

def decrypt_message(token, session_code):
    key = generate_shared_key(session_code)
    f = Fernet(key)
    return f.decrypt(token).decode('utf-8')

class ImageDownloadDialog(QDialog):
    def __init__(self, card_df, set_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Shiny Cardboard!")
        self.setModal(True)
        vbox = QVBoxLayout()
        self.label = QLabel("Downloading shiny cardboard...\nYou only need to wait once per set!")
        self.progress = QProgressBar()
        self.progress.setRange(0, len(card_df))
        self.card_label = QLabel("")
        vbox.addWidget(self.label)
        vbox.addWidget(self.progress)
        vbox.addWidget(self.card_label)
        self.setLayout(vbox)
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)
        self.setMaximumHeight(200)
        self.setMaximumWidth(600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

    def update_progress(self, idx, total, card_name):
        self.progress.setValue(idx)
        self.card_label.setText(f"Downloading: {card_name}")
        QApplication.processEvents()

def download_set_images(card_df, set_id, image_dir='images', parent=None):
    """
    Download all images for a set if not already present.
    Expects card_df to have columns: 'number', 'name', 'image_url'.
    Images are saved as images/<set_id>/<number>_<name>.jpg
    """
    set_dir = os.path.join(image_dir, set_id)
    os.makedirs(set_dir, exist_ok=True)
    dialog = ImageDownloadDialog(card_df, set_id, parent)
    dialog.show()
    total = len(card_df)
    for idx, (_, row) in enumerate(card_df.iterrows(), 1):
        num = str(row['number']).split('/')[0].replace(' ', '')
        name = str(row['name']).replace(' ', '').replace('/', '').replace('?', '')
        img_url = row['image_url']
        ext = os.path.splitext(img_url)[-1] if '.' in img_url else '.jpg'
        fname = f"{num}_{name}{ext}"
        fpath = os.path.join(set_dir, fname)
        dialog.update_progress(idx, total, row['name'])
        if not os.path.exists(fpath):
            try:
                resp = requests.get(img_url, timeout=10)
                resp.raise_for_status()
                with open(fpath, 'wb') as f:
                    f.write(resp.content)
                print(f"[INFO] Downloaded {fname}")
            except Exception as e:
                print(f"[WARN] Could not download {img_url}: {e}")
        else:
            print(f"[INFO] Already have {fname}")
    dialog.close()
    print(f"[INFO] All images for set {set_id} processed.")

def get_set_df_from_parquet(set_id, parquet_path='data/pokemon_cards_all_latest.parquet'):
    """
    Load the card data for a set from the big Parquet file.
    """
    df = pd.read_parquet(parquet_path)
    return df[df['set_id'] == set_id].copy()

class FlowLayout(QHBoxLayout):
    # Simple flow layout for mini cards
    def __init__(self):
        super().__init__()
        self.setSpacing(2)
        self.setContentsMargins(0, 0, 0, 0)

class MiniCardWidget(QWidget):
    def __init__(self, card, thumb_size=(40, 56)):
        super().__init__()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(2, 2, 2, 2)
        img_path = card.get('local_image')
        # Use the full local_image path as is
        name = card.get('name', 'Unknown')
        self.img_label = QLabel()
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path).scaled(*thumb_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.img_label.setPixmap(pixmap)
        else:
            self.img_label.setText("[No Image]")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label = QLabel(name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setFont(QFont('Segoe UI', 7))
        vbox.addWidget(self.img_label)
        vbox.addWidget(name_label)
        self.setLayout(vbox)
        self.setMaximumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
    def set_thumb_size(self, size):
        img_path = self.img_label.pixmap()
        if img_path:
            self.img_label.setPixmap(img_path.scaled(*size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

class CardWidget(QWidget):
    def __init__(self, card, thumb_size=(100, 140)):
        super().__init__()
        self.card = card
        self.eliminated = False
        self.thumb_size = thumb_size
        # print(f"[DEBUG] CardWidget created for: {self.card.get('name', 'Unknown')}, image: {self.card.get('local_image')}")
        self.init_ui()

    def init_ui(self):
        vbox = QVBoxLayout()
        img_path = self.card.get('local_image')
        # Use the full local_image path as is
        name = self.card.get('name', 'Unknown')
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path).scaled(*self.thumb_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.img_label = QLabel()
            self.img_label.setPixmap(pixmap)
            self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.img_label = QLabel("[No Image]")
            self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setFont(QFont('Segoe UI', 9))
        vbox.addWidget(self.img_label)
        vbox.addWidget(self.name_label)
        self.setLayout(vbox)
        self.setAutoFillBackground(True)
        self.update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(self, "Are you sure?", "Are you sure you are ready to guess? (This will eliminate the card)",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                print(f"[DEBUG] Card clicked: {self.card.get('name', 'Unknown')}, eliminated: {self.eliminated}")
                self.toggle_eliminated()
                # Move to history as a guess
                parent = self.parent()
                while parent and not hasattr(parent, 'move_card_to_history'):
                    parent = parent.parent()
                if parent and hasattr(parent, 'move_card_to_history'):
                    parent.move_card_to_history(self.card)
            else:
                print(f"[DEBUG] Card elimination cancelled for: {self.card.get('name', 'Unknown')}")

    def toggle_eliminated(self):
        self.eliminated = not self.eliminated
        print(f"[DEBUG] Card elimination toggled: {self.card.get('name', 'Unknown')} -> {self.eliminated}")
        self.update_style()

    def update_style(self):
        pal = self.palette()
        if self.eliminated:
            pal.setColor(self.backgroundRole(), Qt.GlobalColor.lightGray)
            self.setStyleSheet("opacity: 0.4;")
        else:
            pal.setColor(self.backgroundRole(), Qt.GlobalColor.white)
            self.setStyleSheet("")
        self.setPalette(pal)

class CardGrid(QWidget):
    def __init__(self, cards, on_card_guess=None):
        super().__init__()
        self.cards = cards
        self.card_widgets = []
        self.on_card_guess = on_card_guess
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()
        row, col = 0, 0
        cards_per_row = 6
        for i, card in enumerate(self.cards):
            # print(f"[DEBUG] Adding card to grid: {card.get('name', 'Unknown')} at row {row}, col {col}")
            card_widget = CardWidget(card)
            card_widget.mouseDoubleClickEvent = lambda e, c=card: self.card_double_clicked(c)
            self.card_widgets.append(card_widget)
            layout.addWidget(card_widget, row, col)
            col += 1
            if col >= cards_per_row:
                col = 0
                row += 1
        self.setLayout(layout)

    def card_double_clicked(self, card):
        if self.on_card_guess:
            self.on_card_guess(card)

    def reset_eliminations(self):
        for w in self.card_widgets:
            w.eliminated = False
            w.update_style()

    def eliminate_cards(self, filter_func):
        for w in self.card_widgets:
            if filter_func(w.card):
                w.eliminated = True
                w.update_style()

    def sort_cards_by_elimination(self):
        # Helper to extract card number for sorting
        def card_number(card):
            num = card.get('number', '')
            try:
                return int(num.split('/')[0])
            except Exception:
                return 9999
        # Separate non-eliminated and eliminated
        non_elim = [(w, card_number(w.card)) for w in self.card_widgets if not w.eliminated]
        elim = [(w, card_number(w.card)) for w in self.card_widgets if w.eliminated]
        non_elim.sort(key=lambda x: x[1])
        elim.sort(key=lambda x: x[1])
        # Remove all widgets from layout
        layout = self.layout()
        for i in reversed(range(layout.count())):
            layout.itemAt(i).widget().setParent(None)
        # Add back in sorted order, and ensure eliminated cards are greyed out
        row, col = 0, 0
        cards_per_row = 6
        for w, _ in non_elim:
            w.setEnabled(True)
            w.update_style()
            layout.addWidget(w, row, col)
            col += 1
            if col >= cards_per_row:
                col = 0
                row += 1
        for w, _ in elim:
            w.setEnabled(False)
            w.eliminated = True
            w.update_style()
            layout.addWidget(w, row, col)
            col += 1
            if col >= cards_per_row:
                col = 0
                row += 1

    def remove_eliminated_cards(self):
        # Remove eliminated card widgets from the grid and from card_widgets list
        to_remove = [w for w in self.card_widgets if w.eliminated]
        layout = self.layout()
        for w in to_remove:
            for i in range(layout.count()):
                if layout.itemAt(i).widget() == w:
                    layout.itemAt(i).widget().setParent(None)
                    break
            self.card_widgets.remove(w)

    def move_card_to_history(self, card):
        # Find the GameWindow parent
        parent = self.parent()
        while parent and not hasattr(parent, 'add_history_entry'):
            parent = parent.parent()
        if parent and hasattr(parent, 'add_history_entry'):
            # Remove the card from the grid
            for w in self.card_widgets:
                if w.card == card:
                    w.eliminated = True
                    self.remove_eliminated_cards()
                    break
            # Add to history as a guess
            question = f"Manual guess: {card.get('name', '')}"
            answer = "Eliminated by guess"
            parent.add_history_entry(question, [card], answer_override=answer)

class GameWindow(QWidget):
    def __init__(self, cards, manual_answer=False, selected_card=None):
        super().__init__()
        self.setWindowTitle("Pokémon Card Guesser (PyQt6)")
        self.resize(1200, 900)
        self.cards = cards
        self.remaining_cards = cards.copy()
        self.manual_answer = manual_answer
        # Always select a random card in single player, only use selected_card in manual mode
        if self.manual_answer:
            self.selected_card = selected_card
        else:
            self.selected_card = random.choice(self.cards)
        print(f"[DEBUG] Selected card for this game: {self.selected_card.get('name', 'Unknown')}")
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)
        
        # Left: Selected card panel (only shown in manual mode)
        if self.manual_answer and self.selected_card:
            left_panel = QVBoxLayout()
            secret_card_title = QLabel("<h3>Your Secret Card</h3>")
            secret_card_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left_panel.addWidget(secret_card_title)
            
            # Display the selected card
            card_widget = QWidget()
            card_layout = QVBoxLayout()
            img_label = QLabel()
            img_path = self.selected_card.get('local_image')
            if img_path and os.path.exists(img_path):
                pixmap = QPixmap(img_path).scaled(180, 250, Qt.AspectRatioMode.KeepAspectRatio, 
                                               Qt.TransformationMode.SmoothTransformation)
                img_label.setPixmap(pixmap)
            else:
                img_label.setText("[No Image]")
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            name_label = QLabel(self.selected_card.get('name', 'Unknown'))
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
            
            reminder = QLabel("Answer questions based\non this card!")
            reminder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            reminder.setStyleSheet("color: #FF5722; font-size: 14px; margin-top: 10px;")
            
            card_layout.addWidget(img_label)
            card_layout.addWidget(name_label)
            card_layout.addWidget(reminder)
            card_layout.addStretch()
            card_widget.setLayout(card_layout)
            card_widget.setFixedWidth(200)
            
            left_panel.addWidget(card_widget)
            left_panel.addStretch()
            main_layout.addLayout(left_panel, 0)
            
            # Add a separator
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setLineWidth(1)
            main_layout.addWidget(separator)
            
        # Middle: Main game area (VBox)
        middle_layout = QVBoxLayout()
        # Info and question area
        info_row = QHBoxLayout()
        self.info_label = QLabel(f"Cards remaining: {len(self.cards)}")
        self.info_label.setFont(QFont('Segoe UI', 14, QFont.Weight.Bold))
        info_row.addWidget(self.info_label)
        self.question_entry = QLineEdit()
        self.question_entry.setPlaceholderText("Ask a yes/no question (e.g. Is it a Fire type?)")
        self.question_entry.setFont(QFont('Segoe UI', 12))
        info_row.addWidget(self.question_entry)
        ask_btn = QPushButton("Ask")
        ask_btn.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        ask_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px 24px; border-radius: 8px; margin: 4px;")
        ask_btn.setMinimumHeight(40)
        ask_btn.clicked.connect(self.process_question)
        info_row.addWidget(ask_btn)
        # Connect Enter key to ask question
        self.question_entry.returnPressed.connect(self.process_question)
        # Remove guess card button in manual (multiplayer) mode
        if not self.manual_answer:
            guess_btn = QPushButton("Guess Card")
            guess_btn.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
            guess_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 10px 24px; border-radius: 8px; margin: 4px;")
            guess_btn.setMinimumHeight(40)
            guess_btn.clicked.connect(self.guess_card)
            info_row.addWidget(guess_btn)
        reset_btn = QPushButton("Reset Game")
        reset_btn.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        reset_btn.setStyleSheet("background-color: #FF9800; color: white; padding: 10px 24px; border-radius: 8px; margin: 4px;")
        reset_btn.setMinimumHeight(40)
        reset_btn.clicked.connect(self.reset_game)
        info_row.addWidget(reset_btn)
        middle_layout.addLayout(info_row)

        # Answer area
        self.answer_label = QLabel("")
        self.answer_label.setFont(QFont('Segoe UI', 11))
        middle_layout.addWidget(self.answer_label)

        # Card grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid = CardGrid(self.cards, on_card_guess=self.reveal_card)
        scroll.setWidget(self.grid)
        middle_layout.addWidget(scroll)
        main_layout.addLayout(middle_layout, 3)

        # Right: History panel (fixed width)
        self.history_panel = QVBoxLayout()
        self.history_label = QLabel("History")
        self.history_label.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        self.history_panel.addWidget(self.history_label)
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setMinimumWidth(260)
        self.history_scroll.setMaximumWidth(260)
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.history_widget = QWidget()
        self.history_list = QVBoxLayout()
        self.history_widget.setLayout(self.history_list)
        self.history_scroll.setWidget(self.history_widget)
        self.history_panel.addWidget(self.history_scroll)

        # Add a frame for visual separation
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.VLine)
        frame.setLineWidth(2)
        main_layout.addWidget(frame)

        # Add history panel to main layout
        history_panel_widget = QWidget()
        history_panel_widget.setLayout(self.history_panel)
        main_layout.addWidget(history_panel_widget, 0)

    def process_question(self):
        q = self.question_entry.text().strip().lower()
        print(f"[DEBUG] Question asked: {q}")
        if not q:
            return
        if self.manual_answer:
            reply = QMessageBox.question(self, "Answer Question", f"Q: {q}\nIs the answer YES or NO?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            answer = "Yes" if reply == QMessageBox.StandardButton.Yes else "No"
        else:
            answer = self.answer_for_question(q)
        print(f"[DEBUG] User provided answer: {answer}")
        self.answer_label.setText(f"Q: {q}\nA: {answer}")
        self.last_question = q
        self.last_answer = answer
        self.question_entry.clear()
        eliminated_cards = self.eliminate_by_last_question(auto=True, return_eliminated=True)
        self.add_history_entry(q, eliminated_cards)

    def add_history_entry(self, question, eliminated_cards, answer_override=None):
        answer = answer_override if answer_override is not None else (self.last_answer if hasattr(self, 'last_answer') else '')
        entry_widget = QWidget()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(4, 2, 4, 2)
        vbox.setSpacing(2)
        # Compact Q/A
        qa_row = QHBoxLayout()
        q_label = QLabel(f"Q: {question}")
        q_label.setFont(QFont('Segoe UI', 8, QFont.Weight.Bold))
        a_label = QLabel(f"A: {answer}")
        a_label.setFont(QFont('Segoe UI', 8))
        qa_row.addWidget(q_label)
        qa_row.addWidget(a_label)
        qa_row.addStretch(1)
        vbox.addLayout(qa_row)
        # Grid for cards
        n = max(1, len(eliminated_cards))
        max_width = 220
        card_width = max(18, min(40, max_width // min(n, 5)))
        card_height = int(card_width * 1.4)
        grid_widget = QWidget()
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)
        cards_per_row = 5
        for idx, card in enumerate(eliminated_cards):
            mini = MiniCardWidget(card, thumb_size=(card_width, card_height))
            row = idx // cards_per_row
            col = idx % cards_per_row
            grid.addWidget(mini, row, col)
        grid_widget.setLayout(grid)
        vbox.addWidget(grid_widget)
        entry_widget.setLayout(vbox)
        self.history_list.addWidget(entry_widget)

    def answer_for_question(self, q):
        # Only consider the selected card if it is not eliminated
        for w in self.grid.card_widgets:
            if w.card == self.selected_card and w.eliminated:
                return "No"
        
        # Handle None card or missing data
        card = self.selected_card
        if card is None:
            print("[DEBUG] Selected card is None, defaulting to No")
            return "No"
            
        # Normalize question for steel/metal equivalence
        q_norm = q.replace('steel', 'metal')
        
        # Check for type
        if "type" in q_norm:
            types = card.get('types', [])
            # Handle None types
            if types is None:
                types = []
            for t in types:
                if t is None:
                    continue
                t_norm = t.lower().replace('steel', 'metal')
                print(f"[DEBUG] Checking type: {t_norm}")
                if t_norm in q_norm:
                    return "Yes"
            return "No"
            
        # Check for holo/holographic
        if "holo" in q_norm or "holographic" in q_norm:
            # Accept both the boolean and the rarity string
            holo = card.get('holographic', None)
            rarity = card.get('rarity', '').strip().lower() if card.get('rarity') else ''
            if holo is True or rarity == 'holographic':
                return "Yes"
            return "No"
            
        # Check for rarity
        if "rarity" in q_norm:
            r = card.get('rarity', '') 
            if r is None:
                r = ''
            else:
                r = r.strip().lower()
            print(f"[DEBUG] Checking rarity: {r}")
            import re
            if r and re.search(rf'\b{re.escape(r)}\b', q_norm):
                return "Yes"
            return "No"
            
        # Check for HP
        if "hp" in q_norm:
            import re
            hp = card.get('hp', '')
            print(f"[DEBUG] Checking HP: {hp}")
            # Handle None hp
            if hp is None:
                return "No"
            # Extract integer from both the card's HP and the question
            card_hp = None
            if isinstance(hp, int):
                card_hp = hp
            elif isinstance(hp, str):
                m = re.search(r'(\d+)', hp)
                card_hp = int(m.group(1)) if m else None
            q_hp = None
            m2 = re.search(r'(\d+)', q_norm)
            q_hp = int(m2.group(1)) if m2 else None
            print(f"[DEBUG] Parsed card_hp: {card_hp}, q_hp: {q_hp}")
            if card_hp is not None and q_hp is not None and card_hp == q_hp:
                return "Yes"
            return "No"
            
        # Check for trainer/supporter/stadium/tool in any relevant field
        trainer_keywords = ["trainer", "supporter", "stadium", "tool"]
        for keyword in trainer_keywords:
            if keyword in q_norm:
                ct = card.get('card_type', '') or ''
                if ct is not None:
                    ct = ct.lower().replace('steel', 'metal')
                else:
                    ct = ''
                    
                types = card.get('types', []) or []
                if types is None:
                    types = []
                types = [t.lower().replace('steel', 'metal') if t else '' for t in types]
                    
                name = card.get('name', '') or ''
                if name is not None:
                    name = name.lower().replace('steel', 'metal')
                else:
                    name = ''
                    
                print(f"[DEBUG] Checking for '{keyword}' in card_type: {ct}, types: {types}, name: {name}")
                if keyword in ct or keyword in name or any(keyword in t for t in types if t):
                    return "Yes"
                return "No"
                
        # In manual mode, make the selected card's name unguessable
        if self.manual_answer:
            # If the question is a direct guess of the name, always return No
            if self.selected_card and self.selected_card.get('name'):
                name = self.selected_card['name'].strip().lower()
                if name and name in q.strip().lower():
                    return "No"
        
        # Fallback: check if any word in q_norm is in card fields (with steel/metal normalization)
        for k, v in card.items():
            if v is None:
                continue
            if isinstance(v, str) and v.lower().replace('steel', 'metal') in q_norm:
                print(f"[DEBUG] Fallback match: {k}={v}")
                return "Yes"
        return "No"

    def guess_card(self):
        if self.manual_answer:
            # In manual (multiplayer) mode, guessing is disabled
            QMessageBox.information(self, "Not Allowed", "Guessing is disabled in multiplayer mode. Only the card picker knows the answer!")
            return
        names = [c['name'] for c in self.cards]
        print(f"[DEBUG] Guess card dialog opened. Possible names: {names[:5]}... (total {len(names)})")
        guess, ok = QInputDialog.getItem(self, "Guess the Card", "Which card do you think it is?", names, 0, False)
        if ok and guess:
            print(f"[DEBUG] User guessed: {guess}, actual: {self.selected_card['name']}")
            if guess == self.selected_card['name']:
                QMessageBox.information(self, "Correct!", f"You guessed right! The card was {guess}.")
                self.reset_game()
            else:
                QMessageBox.warning(self, "Incorrect", f"Nope, the card was not {guess}.")

    def reveal_card(self, card):
        print(f"[DEBUG] Card revealed: {card['name']}")
        QMessageBox.information(self, "Card Revealed", f"This is {card['name']}.")

    def reset_game(self):
        # If in manual mode, go back to card selection
        if self.manual_answer:
            QMessageBox.information(self, "Game Reset", "Pick a new secret card to start a new game.")
            from PyQt6.QtCore import QTimer
            def show_card_picker():
                win = FriendManualGameWindow(self.cards)
                win.show()
                # Keep reference to prevent garbage collection
                app = QApplication.instance()
                if hasattr(app, 'references'):
                    app.references.append(win)
            QTimer.singleShot(100, show_card_picker)
            self.close()
            return
        self.selected_card = random.choice(self.cards)
        print(f"[DEBUG] Game reset. New selected card: {self.selected_card.get('name', 'Unknown')}")
        if hasattr(self, 'history_list'):
            while self.history_list.count():
                item = self.history_list.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            reset_widget = QWidget()
            reset_layout = QVBoxLayout()
            reset_label = QLabel("Game Reset")
            reset_label.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
            reset_label.setStyleSheet("color: #FF5722;")
            reset_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            reset_layout.addWidget(reset_label)
            reset_widget.setLayout(reset_layout)
            self.history_list.addWidget(reset_widget)
        scroll = self.findChild(QScrollArea)
        if scroll:
            new_grid = CardGrid(self.cards, on_card_guess=self.reveal_card)
            scroll.setWidget(new_grid)
            self.grid = new_grid
        else:
            self.grid.reset_eliminations()
        self.answer_label.setText("")
        self.info_label.setText(f"Cards remaining: {len(self.cards)}")
        self.question_entry.clear()
        QMessageBox.information(self, "Game Reset", "The game has been reset with a new secret card.")

    def eliminate_by_last_question(self, auto=False, return_eliminated=False):
        if not hasattr(self, 'last_question') or not hasattr(self, 'last_answer'):
            if not auto:
                QMessageBox.warning(self, "No Question", "Ask a question first!")
            return [] if return_eliminated else None
        q = self.last_question
        a = self.last_answer
        print(f"[DEBUG] Eliminating cards based on: Q: {q} | A: {a}")
        eliminated_cards = []
        # Only consider non-eliminated cards for elimination
        def filter_func(card):
            # Find the widget for this card
            for w in self.grid.card_widgets:
                if w.card == card and not w.eliminated:
                    gw = GameWindow([card])
                    gw.selected_card = card
                    ans = gw.answer_for_question(q)
                    print(f"[DEBUG] Card {card.get('name','?')} would answer: {ans}")
                    if a == "Yes" and ans == "No":
                        eliminated_cards.append(card)
                        return True
                    if a == "No" and ans == "Yes":
                        eliminated_cards.append(card)
                        return True
            return False
        self.grid.eliminate_cards(filter_func)
        # Remove eliminated cards from the grid and card_widgets
        self.grid.remove_eliminated_cards()
        # Update info label
        remaining = sum(1 for w in self.grid.card_widgets if not w.eliminated)
        self.info_label.setText(f"Cards remaining: {remaining}")
        # Sort the grid after elimination
        self.grid.sort_cards_by_elimination()
        if return_eliminated:
            return eliminated_cards
        return None

class SplashScreen(QWidget):
    def __init__(self, on_set_selected):
        super().__init__()
        self.on_set_selected = on_set_selected
        self.setWindowTitle("Welcome to Pokémon Card Guesser!")
        self.setMinimumSize(900, 700)
        layout = QVBoxLayout()
        title = QLabel("<h1>Pokémon Card Guesser</h1>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        info = QLabel('<b>Note:</b> Loading the set list and logos may take up to 30 seconds on first launch.')
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)
        credit = QLabel('<a href="https://www.pokemon.com">Pokémon images © Nintendo/Creatures Inc./GAME FREAK inc.</a>')
        credit.setOpenExternalLinks(True)
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(credit)
        # Replace privacy link with plain text
        privacy = QLabel('This app does not collect or share any personal data. All card data is sourced from public web resources. For questions, contact the developer.')
        privacy.setWordWrap(True)
        privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(privacy)
        sets_label = QLabel("<b>Select a set to play:</b>")
        sets_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sets_label)
        self.sets_grid = QGridLayout()
        self.sets_grid.setSpacing(12)
        layout.addLayout(self.sets_grid)
        self.setLayout(layout)
        # Use QTimer to load sets after splash is shown
        QTimer.singleShot(100, self.load_sets)

    def load_sets(self):
        # Show a loading dialog while fetching set info and logos
        loading_dialog = ProgressDialog("Welcome! Loading set list and logos...")
        loading_dialog.show()
        QApplication.processEvents()
        sets = self.get_english_set_links()
        os.makedirs('images/assets/set_logos', exist_ok=True)
        # Check if all set logos are already downloaded
        logo_files = set(os.listdir('images/assets/set_logos'))
        expected_logos = set(os.path.basename(s['logo_url']) for s in sets if s['logo_url'])
        if expected_logos.issubset(logo_files):
            loading_dialog.close()
            self.display_sets(sets)
            return
        # Download missing logos
        for s in sets:
            logo_path = None
            logo_url = s.get('logo_url')
            if logo_url:
                logo_filename = os.path.basename(logo_url)
                logo_path = os.path.join('images', 'assets', 'set_logos', logo_filename)
                if not os.path.exists(logo_path):
                    try:
                        from urllib.request import urlretrieve
                        urlretrieve(logo_url, logo_path)
                    except Exception:
                        logo_path = None
        loading_dialog.close()
        self.display_sets(sets)

    def display_sets(self, sets):
        # Make the set grid scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_widget = QWidget()
        grid_layout = QGridLayout()
        grid_layout.setSpacing(12)
        row, col = 0, 0
        sets_per_row = 4
        for s in sets:
            logo_path = None
            logo_url = s.get('logo_url')
            if logo_url:
                logo_filename = os.path.basename(logo_url)
                logo_path = os.path.join('images', 'assets', 'set_logos', logo_filename)
            btn = QPushButton()
            btn.setMinimumSize(160, 80)
            btn.setMaximumSize(180, 100)
            # Remove the set name text, only show logo
            if logo_path and os.path.exists(logo_path):
                pixmap = QPixmap(logo_path).scaled(100, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                btn.setIcon(QIcon(pixmap))
                btn.setIconSize(QSize(100, 50))
            btn.setStyleSheet("QPushButton { padding-left: 8px; }")
            btn.clicked.connect(lambda checked, url=s['url']: self.on_set_selected(url))
            grid_layout.addWidget(btn, row, col)
            col += 1
            if col >= sets_per_row:
                col = 0
                row += 1
        grid_widget.setLayout(grid_layout)
        scroll.setWidget(grid_widget)
        # Remove old grid if present
        if hasattr(self, 'sets_grid_widget'):
            self.layout().removeWidget(self.sets_grid_widget)
            self.sets_grid_widget.deleteLater()
        self.sets_grid_widget = scroll
        self.layout().addWidget(scroll)

    def get_set_logo_url(self, set_url):
        try:
            resp = requests.get(set_url)
            soup = BeautifulSoup(resp.text, 'html.parser')
            meta = soup.find('meta', property='og:image')
            if meta and meta.get('content'):
                return meta['content']
        except Exception:
            pass
        return None

    def get_english_set_links(self):
        url = "https://www.serebii.net/card/english.shtml"
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        sets = []
        # Find the main table with all sets
        main_table = None
        for table in soup.find_all('table'):
            headers = [th.get_text(strip=True).lower() for th in table.find_all('td')[:5]]
            if 'set name' in ''.join(headers).lower() and 'number of cards' in ''.join(headers).lower():
                main_table = table
                break
        if not main_table:
            return sets
        for row in main_table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) < 5:
                continue
            # Set detail page
            set_link = cells[2].find('a')
            set_name = set_link.get_text(strip=True) if set_link else ''
            set_url = f"https://www.serebii.net{set_link['href']}" if set_link and set_link.has_attr('href') else ''
            # Set logo
            logo_img = cells[0].find('img')
            logo_url = f"https://www.serebii.net{logo_img['src']}" if logo_img and logo_img.has_attr('src') else ''
            # Number of cards
            num_cards = cells[3].get_text(strip=True)
            # Release date
            release_date = cells[4].get_text(strip=True)
            if set_url and set_name:
                sets.append({
                    'name': set_name,
                    'url': set_url,
                    'logo_url': logo_url,
                    'num_cards': num_cards,
                    'release_date': release_date
                })
        return sets

class ScrapeThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool)
    def __init__(self, set_url, csv_path):
        super().__init__()
        self.set_url = set_url
        self.csv_path = csv_path
    def run(self):
        self.progress.emit("Starting scraper...")
        try:
            # Run the scraping logic directly in this thread
            from scraper.serebii_card_scraper import SerebiiCardScraper
            scraper = SerebiiCardScraper(set_url=self.set_url)
            cards = scraper.scrape_cards_to_csv(self.csv_path)
            self.progress.emit("Done.")
            self.finished.emit(True)
        except Exception as e:
            self.progress.emit(f"Error: {e}")
            self.finished.emit(False)

class ProgressDialog(QDialog):
    def __init__(self, message="Working..."):
        super().__init__()
        self.setWindowTitle("Please Wait")
        self.setModal(True)
        layout = QVBoxLayout()
        self.label = QLabel(message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        self.setLayout(layout)
        self.setMinimumWidth(400)
    def update_message(self, msg):
        self.label.setText(msg)

class ModeSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Game Mode")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMaximumWidth(500)
        vbox = QVBoxLayout()
        title = QLabel("<h2>How do you want to play?</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(title)
        single_btn = QPushButton("Single Player")
        single_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 18px; padding: 16px; border-radius: 10px;")
        friend_btn = QPushButton("Play with a Friend")
        friend_btn.setStyleSheet("background-color: #2196F3; color: white; font-size: 18px; padding: 16px; border-radius: 10px;")
        vbox.addWidget(single_btn)
        vbox.addWidget(friend_btn)
        self.setLayout(vbox)
        self.selected_mode = None
        single_btn.clicked.connect(self.choose_single)
        friend_btn.clicked.connect(self.choose_friend)
    def choose_single(self):
        self.selected_mode = 'single'
        self.accept()
    def choose_friend(self):
        self.selected_mode = 'friend'
        self.accept()

class FriendManualGameWindow(QWidget):
    def __init__(self, cards):
        print("[DEBUG] FriendManualGameWindow __init__ called")
        super().__init__()
        self.setWindowTitle("Pokémon Card Guesser - Play with a Friend (Manual)")
        self.resize(1200, 900)
        self.cards = cards
        self.selected_card = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()  # Change to horizontal layout
        
        # Left panel for selected card display
        left_panel = QVBoxLayout()
        title = QLabel("<h2>Your Secret Card</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_panel.addWidget(title)
        
        # Card display widget
        self.selected_card_widget = QWidget()
        card_layout = QVBoxLayout()
        self.card_image = QLabel()
        self.card_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_name = QLabel()
        self.card_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_name.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        
        reminder = QLabel("Remember: Answer your\nfriend's questions based\non this card!")
        reminder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reminder.setStyleSheet("color: #FF5722; font-size: 14px; margin-top: 20px;")
        
        card_layout.addWidget(self.card_image)
        card_layout.addWidget(self.card_name)
        card_layout.addWidget(reminder)
        card_layout.addStretch()
        
        self.selected_card_widget.setLayout(card_layout)
        self.selected_card_widget.setMinimumWidth(220)
        self.selected_card_widget.setMaximumWidth(250)
        self.selected_card_widget.hide()  # Hide until card is selected
        
        left_panel.addWidget(self.selected_card_widget)
        left_panel.addStretch()
        
        # Right panel for card selection
        right_panel = QVBoxLayout()

        # Add card selection mode at the top
        mode_row = QHBoxLayout()
        mode_label = QLabel("How do you want to select the secret card?")
        mode_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        mode_row.addWidget(mode_label)
        self.pick_mode_btn = QPushButton("Pick Myself")
        self.pick_mode_btn.setCheckable(True)
        self.pick_mode_btn.setChecked(True)
        self.pick_mode_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 13px; padding: 6px 18px; border-radius: 8px;")
        self.random_mode_btn = QPushButton("Random Card")
        self.random_mode_btn.setCheckable(True)
        self.random_mode_btn.setStyleSheet("background-color: #2196F3; color: white; font-size: 13px; padding: 6px 18px; border-radius: 8px;")
        mode_row.addWidget(self.pick_mode_btn)
        mode_row.addWidget(self.random_mode_btn)
        mode_row.addStretch(1)
        # Button group logic
        def set_pick():
            self.pick_mode_btn.setChecked(True)
            self.random_mode_btn.setChecked(False)
            self.card_grid.setEnabled(True)
        def set_random():
            self.pick_mode_btn.setChecked(False)
            self.random_mode_btn.setChecked(True)
            self.card_grid.setEnabled(False)
            # Pick a random card and show confirmation
            card = random.choice(self.cards)
            self.selected_card = card
            self.update_selected_card_display()
            reply = QMessageBox.question(
                self,
                "Random Card Selected",
                f"A random card was selected: {card.get('name', 'Unknown')}. Use this card?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.confirm_card()
            else:
                self.selected_card = None
                self.card_name.setText("")
                self.card_image.clear()
                self.selected_card_widget.hide()
                self.pick_mode_btn.setChecked(True)
                self.random_mode_btn.setChecked(False)
                self.card_grid.setEnabled(True)
        self.pick_mode_btn.clicked.connect(set_pick)
        self.random_mode_btn.clicked.connect(set_random)
        right_panel.addLayout(mode_row)

        selection_title = QLabel("<h2>Play with a Friend (Manual Mode)</h2>")
        selection_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_panel.addWidget(selection_title)
        
        desc = QLabel("Pick your card from the grid below, then answer your friend's questions with Yes/No.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 16px; margin: 12px;")
        right_panel.addWidget(desc)
        
        # Card selection - Use a grid view instead of a dropdown
        pick_label = QLabel("Click to select your card (hidden from your friend):")
        pick_label.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        pick_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_panel.addWidget(pick_label)
        
        # Scrollable card grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.card_grid = QWidget()
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        
        row, col = 0, 0
        cards_per_row = 6
        
        for i, card in enumerate(self.cards):
            card_widget = self.create_selectable_card_widget(card)
            grid_layout.addWidget(card_widget, row, col)
            col += 1
            if col >= cards_per_row:
                col = 0
                row += 1
        
        self.card_grid.setLayout(grid_layout)
        scroll.setWidget(self.card_grid)
        right_panel.addWidget(scroll)
        
        # Add both panels to main layout
        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 3)
        self.setLayout(main_layout)

    def create_selectable_card_widget(self, card):
        """Create a clickable card widget for the selection grid"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Card image
        img_path = card.get('local_image')
        name = card.get('name', 'Unknown')
        
        img_label = QLabel()
        thumb_size = (100, 140)
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path).scaled(*thumb_size, Qt.AspectRatioMode.KeepAspectRatio, 
                                             Qt.TransformationMode.SmoothTransformation)
            img_label.setPixmap(pixmap)
        else:
            img_label.setText("[No Image]")
        
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Card name
        name_label = QLabel(name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setFont(QFont('Segoe UI', 9))
        
        layout.addWidget(img_label)
        layout.addWidget(name_label)
        widget.setLayout(layout)
        
        # Style for hover effect
        widget.setStyleSheet("""
            QWidget { background-color: #f0f0f0; border-radius: 8px; }
            QWidget:hover { background-color: #e0e0e0; border: 2px solid #4CAF50; }
        """)
        
        # Connect click event
        widget.mousePressEvent = lambda e, c=card: self.card_selected(c)
        
        return widget

    def card_selected(self, card):
        """Handle card selection from the grid"""
        print(f"[DEBUG] Card selected: {card.get('name', 'Unknown')}")
        
        # Show confirmation popup
        reply = QMessageBox.question(
            self, 
            "Confirm Card Selection", 
            f"Do you want to select {card.get('name', 'Unknown')} as your card?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.selected_card = card
            self.update_selected_card_display()
            self.confirm_card()
    
    def update_selected_card_display(self):
        """Update the left panel with the selected card"""
        if not self.selected_card:
            return
            
        img_path = self.selected_card.get('local_image')
        name = self.selected_card.get('name', 'Unknown')
        
        # Set card image
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path).scaled(200, 280, Qt.AspectRatioMode.KeepAspectRatio, 
                                           Qt.TransformationMode.SmoothTransformation)
            self.card_image.setPixmap(pixmap)
        else:
            self.card_image.setText("[No Image]")
            
        # Set card name
        self.card_name.setText(name)
        
        # Show the card display
        self.selected_card_widget.show()

    def confirm_card(self):
        print("[DEBUG] FriendManualGameWindow confirm_card called")
        QMessageBox.information(
            self, 
            "Card Selected", 
            f"You picked: {self.selected_card['name']}\nNow answer your friend's questions with Yes/No. Eliminate cards as you go!"
        )
        print("[DEBUG] Launching GameWindow from FriendManualGameWindow")
        # Launch GameWindow in manual answer mode
        win = GameWindow(self.cards, manual_answer=True, selected_card=self.selected_card)
        win.show()
        print(f"[DEBUG] GameWindow shown: {win}")
        self.close()
        self._child_window = win

    def showEvent(self, event):
        print("[DEBUG] FriendManualGameWindow showEvent called")
        super().showEvent(event)

    def closeEvent(self, event):
        print("[DEBUG] FriendManualGameWindow closeEvent called")
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    
    # Create a global variable to store references to windows
    # This prevents them from being garbage collected
    app.references = []
    
    def start_game_with_set(set_url):
        set_id = set_url.rstrip('/').split('/')[-1]
        parquet_path = 'data/pokemon_cards_all_latest.parquet'  # Update to your latest file
        card_df = get_set_df_from_parquet(set_id, parquet_path)
        if card_df.empty:
            QMessageBox.critical(None, "Error", f"No card data found for set {set_id} in the Parquet file.")
            return
        download_set_images(card_df, set_id, parent=splash)
        set_dir = os.path.join('images', set_id)
        for i, row in card_df.iterrows():
            num = str(row['number']).split('/')[0].replace(' ', '')
            name = str(row['name']).replace(' ', '').replace('/', '').replace('?', '')
            ext = os.path.splitext(row['image_url'])[-1] if '.' in row['image_url'] else '.jpg'
            fname = f"{num}_{name}{ext}"
            card_df.at[i, 'local_image'] = os.path.join(set_dir, fname)
        cards = card_df.to_dict(orient='records')
        mode_dialog = ModeSelectDialog(parent=splash)
        if mode_dialog.exec() == QDialog.DialogCode.Accepted:
            if mode_dialog.selected_mode == 'single':
                print("[DEBUG] Opening GameWindow (single player mode)")
                win = GameWindow(cards)
                win.show()
                # Keep reference to prevent garbage collection
                app.references.append(win)
            elif mode_dialog.selected_mode == 'friend':
                print("[DEBUG] Opening FriendManualGameWindow (play with a friend mode)")
                try:
                    # Create window
                    friend_win = FriendManualGameWindow(cards)
                    # Keep reference to prevent garbage collection
                    app.references.append(friend_win)
                    # Show window and make sure it's on top
                    friend_win.show()
                    friend_win.raise_()
                    friend_win.activateWindow()
                    print("[DEBUG] FriendManualGameWindow creation successful")
                except Exception as e:
                    print(f"[ERROR] Failed to open FriendManualGameWindow: {e}")
                    import traceback
                    traceback.print_exc()
    
    splash = SplashScreen(on_set_selected=start_game_with_set)
    splash.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
