import cv2
import pytesseract
import re

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

img = cv2.imread('test_plate.jpeg')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
text = pytesseract.image_to_string(thresh, lang='rus', config='--psm 8')
print('Raw:', text)
plate = re.sub(r'[^A-Z0-9А-Я]', '', text).strip()
print('Plate:', plate)