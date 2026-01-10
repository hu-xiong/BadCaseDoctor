from flask import Blueprint, request, jsonify
from agents.ocr_agent import perform_ocr
from PIL import Image

ocr_router = Blueprint('ocr', __name__)

@ocr_router.route('/ocr', methods=['POST'])
def ocr():
    if 'image' not in request.files:
        return jsonify({"code": 400, "message": "No image file provided"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"code": 400, "message": "Empty filename"}), 400

    # 支持的语言（默认中英文）
    lang = request.form.get('lang', 'chi_sim+eng')  # 可通过 form-data 传 lang=eng 等

    try:
        image = Image.open(file.stream).convert('RGB')
        text = perform_ocr(image, lang=lang)
        return jsonify({
            "code": 200,
            "message": "success",
            "text": text
        })
    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"OCR processing failed: {str(e)}"
        }), 500