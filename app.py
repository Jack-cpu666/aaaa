from flask import Flask, render_template_string, jsonify, request
import json
import base64
import qrcode
import io
import base64
from datetime import datetime

app = Flask(__name__)

# NFC tag data from your screenshots
NFC_DATA = {
    "tagType": "NTAG213",
    "manufacturer": "NXP", 
    "iso": "ISO 14443-3A",
    "serialNumber": "04:25:B4:3A:F3:1C:90",
    "atqa": "0x0044",
    "sak": "0x00",
    "text": "10151846",
    "language": "en",
    "encoding": "UTF-8",
    "payload_hex": "02 65 6E 31 30 31 35 31 38 34 36",
    "payload_bytes": [0x02, 0x65, 0x6E, 0x31, 0x30, 0x31, 0x35, 0x31, 0x38, 0x34, 0x36],
    "memorySize": 180,
    "pages": 45,
    "pageSize": 4,
    "recordType": "Text record: T (0x54)",
    "format": "NFC Well Known (0x01)",
    "rfc": "Defined by RFC 2141, RFC 3986"
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NFC Tag Emulator - NTAG213</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 500px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 30px 20px;
            text-align: center;
        }

        .nfc-icon {
            width: 60px;
            height: 60px;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 15px;
            font-size: 30px;
        }

        .status {
            padding: 20px;
            text-align: center;
        }

        .status-indicator {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 10px;
            animation: pulse 2s infinite;
        }

        .status-active {
            background: #4CAF50;
        }

        .status-inactive {
            background: #f44336;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        .tag-details {
            padding: 0 20px;
        }

        .detail-group {
            margin-bottom: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #2a5298;
        }

        .detail-label {
            font-weight: 600;
            color: #555;
            font-size: 14px;
            margin-bottom: 5px;
        }

        .detail-value {
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            color: #2a5298;
            font-size: 16px;
        }

        .payload-hex {
            word-break: break-all;
            line-height: 1.4;
        }

        .qr-section {
            padding: 20px;
            text-align: center;
            background: #f8f9fa;
        }

        .qr-code {
            margin: 20px auto;
            padding: 15px;
            background: white;
            border-radius: 10px;
            display: inline-block;
        }

        .qr-code img {
            border-radius: 5px;
        }

        .actions {
            padding: 20px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .btn {
            flex: 1;
            min-width: 120px;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .btn-primary {
            background: #2a5298;
            color: white;
        }

        .btn-primary:hover {
            background: #1e3c72;
            transform: translateY(-2px);
        }

        .btn-secondary {
            background: #e9ecef;
            color: #495057;
        }

        .btn-secondary:hover {
            background: #dee2e6;
        }

        .web-nfc-section {
            padding: 20px;
            border-top: 1px solid #e9ecef;
        }

        .warning {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            color: #856404;
        }

        .success-message {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
            color: #155724;
            display: none;
        }

        .error-message {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
            color: #721c24;
            display: none;
        }

        .api-section {
            padding: 20px;
            border-top: 1px solid #e9ecef;
            background: #f8f9fa;
        }

        .api-endpoint {
            background: #343a40;
            color: #f8f9fa;
            padding: 10px 15px;
            border-radius: 5px;
            font-family: monospace;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="nfc-icon">📡</div>
            <h1>NFC Tag Emulator</h1>
            <p>{{ nfc_data.tagType }} - {{ nfc_data.iso }}</p>
        </div>

        <div class="status">
            <div class="status-indicator status-active"></div>
            <span>Emulation Active</span>
        </div>

        <div class="tag-details">
            <div class="detail-group">
                <div class="detail-label">Tag Type</div>
                <div class="detail-value">{{ nfc_data.tagType }} ({{ nfc_data.manufacturer }})</div>
            </div>

            <div class="detail-group">
                <div class="detail-label">Serial Number</div>
                <div class="detail-value">{{ nfc_data.serialNumber }}</div>
            </div>

            <div class="detail-group">
                <div class="detail-label">Text Content</div>
                <div class="detail-value">{{ nfc_data.text }}</div>
            </div>

            <div class="detail-group">
                <div class="detail-label">NDEF Record Type</div>
                <div class="detail-value">{{ nfc_data.recordType }}</div>
            </div>

            <div class="detail-group">
                <div class="detail-label">Raw Payload (Hex)</div>
                <div class="detail-value payload-hex">{{ nfc_data.payload_hex }}</div>
            </div>

            <div class="detail-group">
                <div class="detail-label">Memory Size</div>
                <div class="detail-value">{{ nfc_data.memorySize }} bytes ({{ nfc_data.pages }} pages × {{ nfc_data.pageSize }} bytes)</div>
            </div>

            <div class="detail-group">
                <div class="detail-label">ATQA / SAK</div>
                <div class="detail-value">{{ nfc_data.atqa }} / {{ nfc_data.sak }}</div>
            </div>
        </div>

        <div class="qr-section">
            <h3>QR Code Alternative</h3>
            <p>Scan this QR code to get the same data</p>
            <div class="qr-code">
                <img src="/qr" alt="QR Code" />
            </div>
        </div>

        <div class="web-nfc-section">
            <h3>Web NFC (Experimental)</h3>
            <div class="warning">
                ⚠️ Web NFC is only supported on some Android browsers and cannot emulate tags on iOS
            </div>
            
            <div class="success-message" id="success-msg">
                ✅ NFC operation successful!
            </div>
            
            <div class="error-message" id="error-msg">
                ❌ <span id="error-text"></span>
            </div>

            <div class="actions">
                <button class="btn btn-primary" onclick="tryWebNFC()">Try Web NFC Write</button>
                <button class="btn btn-secondary" onclick="copyData()">Copy Data</button>
                <button class="btn btn-secondary" onclick="downloadData()">Download JSON</button>
            </div>
        </div>

        <div class="api-section">
            <h3>API Endpoints</h3>
            <p>Access NFC data programmatically:</p>
            <div class="api-endpoint">GET /api/nfc - Get full NFC data</div>
            <div class="api-endpoint">GET /api/text - Get text content only</div>
            <div class="api-endpoint">GET /api/payload - Get raw payload</div>
        </div>
    </div>

    <script>
        // Get NFC data from server
        const nfcData = {{ nfc_data_json | safe }};

        // Try Web NFC API (experimental)
        async function tryWebNFC() {
            const successMsg = document.getElementById('success-msg');
            const errorMsg = document.getElementById('error-msg');
            const errorText = document.getElementById('error-text');

            successMsg.style.display = 'none';
            errorMsg.style.display = 'none';

            if (!('NDEFReader' in window)) {
                errorText.textContent = 'Web NFC is not supported in this browser';
                errorMsg.style.display = 'block';
                return;
            }

            try {
                const ndef = new NDEFReader();
                
                // Create NDEF message with text record
                const message = {
                    records: [{
                        recordType: "text",
                        lang: nfcData.language,
                        data: nfcData.text
                    }]
                };

                await ndef.write(message);
                successMsg.style.display = 'block';
                
            } catch (error) {
                errorText.textContent = error.message;
                errorMsg.style.display = 'block';
            }
        }

        // Copy data to clipboard
        function copyData() {
            const dataString = `NFC Tag Data:
Tag Type: ${nfcData.tagType}
Serial: ${nfcData.serialNumber}
Text: ${nfcData.text}
Raw Payload: ${nfcData.payload_hex}
ATQA: ${nfcData.atqa}
SAK: ${nfcData.sak}`;

            navigator.clipboard.writeText(dataString).then(() => {
                alert('NFC data copied to clipboard!');
            });
        }

        // Download data as JSON
        function downloadData() {
            const dataStr = JSON.stringify(nfcData, null, 2);
            const dataBlob = new Blob([dataStr], {type: 'application/json'});
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'nfc_tag_data.json';
            link.click();
            URL.revokeObjectURL(url);
        }

        // Simulate NFC scanning animation
        setInterval(() => {
            const indicator = document.querySelector('.status-indicator');
            indicator.style.transform = 'scale(1.2)';
            setTimeout(() => {
                indicator.style.transform = 'scale(1)';
            }, 200);
        }, 3000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main page with NFC emulator"""
    return render_template_string(HTML_TEMPLATE, 
                                nfc_data=NFC_DATA, 
                                nfc_data_json=json.dumps(NFC_DATA))

@app.route('/qr')
def generate_qr():
    """Generate QR code for the NFC text data"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(NFC_DATA['text'])
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    from flask import Response
    return Response(img_buffer.getvalue(), mimetype='image/png')

@app.route('/api/nfc')
def api_nfc_data():
    """API endpoint to get full NFC data"""
    response = NFC_DATA.copy()
    response['timestamp'] = datetime.now().isoformat()
    response['status'] = 'active'
    return jsonify(response)

@app.route('/api/text')
def api_text_only():
    """API endpoint to get text content only"""
    return jsonify({
        'text': NFC_DATA['text'],
        'language': NFC_DATA['language'],
        'encoding': NFC_DATA['encoding'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/payload')
def api_payload():
    """API endpoint to get raw payload data"""
    return jsonify({
        'payload_hex': NFC_DATA['payload_hex'],
        'payload_bytes': NFC_DATA['payload_bytes'],
        'payload_base64': base64.b64encode(bytes(NFC_DATA['payload_bytes'])).decode('utf-8'),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/emulate', methods=['POST'])
def api_emulate():
    """API endpoint to simulate NFC tag emulation"""
    data = request.get_json()
    
    # Log the emulation request
    emulation_log = {
        'timestamp': datetime.now().isoformat(),
        'client_ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'requested_data': data,
        'emulated_tag': NFC_DATA['tagType'],
        'emulated_text': NFC_DATA['text']
    }
    
    return jsonify({
        'status': 'success',
        'message': 'NFC tag emulation simulated',
        'emulated_data': NFC_DATA,
        'log': emulation_log
    })

@app.route('/health')
def health_check():
    """Health check endpoint for deployment"""
    return jsonify({
        'status': 'healthy',
        'service': 'NFC Tag Emulator',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    # For local development
    app.run(debug=True, host='0.0.0.0', port=5000)
    
# For deployment on Render.com, also include:
# if __name__ == '__main__':
#     import os
#     port = int(os.environ.get('PORT', 5000))
#     app.run(host='0.0.0.0', port=port)