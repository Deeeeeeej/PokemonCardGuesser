# Pokémon Card Guesser

A desktop game for playing Pokémon "Guess Who" with real TCG cards! Supports single player and local multiplayer (manual answer) modes.

## Features
- Play with any official Pokémon TCG set (auto-scraped from Serebii)
- Single player (AI answers questions)
- Multiplayer (play with a friend, manual Yes/No answers)
- Modern PyQt6 interface
- No network/IP sharing required
- Card images and set logos auto-downloaded

## Installation

1. **Clone the repository**

```sh
# Using HTTPS
git clone https://github.com/yourusername/PokemonCardGuesser.git
cd PokemonCardGuesser
```

2. **Install dependencies**

It's recommended to use a virtual environment:

```sh
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

3. **Run the game**

```sh
python card_guesser.py
```

## Requirements
- Python 3.9+
- See `requirements.txt` for all dependencies

## Notes
- All card data and images are sourced from public web resources.
- No personal data is collected or shared.

## License
This project is for educational and personal use. Pokémon images © Nintendo/Creatures Inc./GAME FREAK inc.

---

For questions or issues, open an issue on GitHub or contact the developer.
