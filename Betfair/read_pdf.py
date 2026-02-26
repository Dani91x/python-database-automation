import pypdf
import os

pdf_path = r"c:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\Betfair\Betfair_api_documentation.pdf"
output_path = r"c:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\Betfair\documentation_text.txt"

def extract_text():
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found")
        return

    reader = pypdf.PdfReader(pdf_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(reader.pages):
            f.write(f"--- PAGE {i+1} ---\n")
            f.write(page.extract_text())
            f.write("\n\n")
    print(f"Extraction complete. Saved to {output_path}")

if __name__ == "__main__":
    extract_text()
