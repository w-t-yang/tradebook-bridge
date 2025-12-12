import csv
import json
import os

def to_fixed_format(symbol: str) -> str:
    """
    Converts a symbol to the fixed format: SH/SZ + 6 digits.
    Same logic as in hybrid_server.py
    """
    symbol = symbol.strip().upper()
    
    # Handle yfinance format (.SS, .SZ)
    if symbol.endswith('.SS'):
        return f"SH{symbol[:-3]}"
    if symbol.endswith('.SZ'):
        return f"SZ{symbol[:-3]}"
    
    # Handle already compatible format (SH/SZ + 6 digits)
    if (symbol.startswith('SH') or symbol.startswith('SZ')) and len(symbol) == 8 and symbol[2:].isdigit():
        return symbol

    # Handle pure 6 digits
    if symbol.isdigit() and len(symbol) == 6:
        if symbol.startswith('6'):
            return f"SH{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            return f"SZ{symbol}"
        
    return symbol

def generate_json_map():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "tmp", "stock_zh_a_spot_em.csv")
    data_dir = os.path.join(base_dir, "data")
    json_path = os.path.join(data_dir, "cn_stock_names.json")

    if not os.path.exists(csv_path):
        print(f"Error: CSV not found at {csv_path}")
        return

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    symbol_map = {}

    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get('代码')
                name = row.get('名称')
                if code and name:
                    # Store original code (uppercased)
                    code_upper = code.strip().upper()
                    symbol_map[code_upper] = name
                    
                    # Store fixed format if applicable
                    if code.isdigit() and len(code) == 6:
                        fixed = to_fixed_format(code)
                        # fixed is already uppercased by function
                        symbol_map[fixed] = name
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(symbol_map, f, ensure_ascii=False, indent=2)
            
        print(f"Successfully generated {json_path} with {len(symbol_map)} entries.")

    except Exception as e:
        print(f"Error generating map: {e}")

if __name__ == "__main__":
    generate_json_map()
