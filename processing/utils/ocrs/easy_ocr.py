import easyocr


class EasyOcrEngine:

    def __init__(self):
        self.reader = easyocr.Reader(['ru', 'en'])

    def recognize(self, value) -> str | None:

        if not (result := self.reader.recognize(value)):
            return None
        if not (result := [r for r in result if r[2] > 0.4]):
            return None
        result.sort(key=lambda x: x[0][0][0])
        text = ''.join([r[1] for r in result])
        return text.strip().upper()

