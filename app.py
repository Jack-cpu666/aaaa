from flask import Flask, render_template_string, jsonify, request, send_file, Response
import json
import base64
import qrcode
import io
import zipfile
import hashlib
import time
from datetime import datetime
import os
import tempfile

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
    <title>NFC Digital Wallet Card</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            margin: 0 auto;
        }

        .card-preview {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            color: white;
            position: relative;
            overflow: hidden;
        }

        .card-preview::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
            transform: rotate(45deg);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .card-title {
            font-size: 18px;
            font-weight: 600;
        }

        .nfc-icon {
            font-size: 24px;
            background: rgba(255, 255, 255, 0.2);
            padding: 8px;
            border-radius: 8px;
        }

        .card-content {
            position: relative;
            z-index: 2;
        }

        .main-text {
            font-size: 32px;
            font-weight: 700;
            letter-spacing: 2px;
            margin: 20px 0;
            text-align: center;
        }

        .card-details {
            font-size: 12px;
            opacity: 0.8;
            margin-top: 15px;
        }

        .card-serial {
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 10px;
            margin-top: 10px;
        }

        .controls {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
        }

        .add-to-wallet {
            background: #000;
            color: white;
            border: none;
            border-radius: 12px;
            padding: 15px 25px;
            width: 100%;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 15px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            transition: all 0.3s ease;
        }

        .add-to-wallet:hover {
            background: #333;
            transform: translateY(-2px);
        }

        .add-to-wallet:active {
            transform: translateY(0);
        }

        .wallet-icon {
            width: 20px;
            height: 20px;
            background: white;
            border-radius: 3px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: black;
            font-size: 12px;
        }

        .alternative-methods {
            margin-top: 20px;
        }

        .method {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 4px solid #2a5298;
        }

        .method-title {
            font-weight: 600;
            color: #2a5298;
            margin-bottom: 5px;
        }

        .method-desc {
            font-size: 14px;
            color: #666;
        }

        .qr-code {
            text-align: center;
            margin: 15px 0;
        }

        .qr-code img {
            border-radius: 8px;
            background: white;
            padding: 10px;
        }

        .status {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 20px;
            color: #155724;
            text-align: center;
        }

        .instructions {
            background: #e3f2fd;
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
            font-size: 14px;
            color: #1565c0;
        }

        .btn-secondary {
            background: #e9ecef;
            color: #495057;
            border: none;
            border-radius: 8px;
            padding: 10px 15px;
            margin: 5px;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .btn-secondary:hover {
            background: #dee2e6;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Card Preview -->
        <div class="card-preview">
            <div class="card-header">
                <div class="card-title">NFC Digital Card</div>
                <div class="nfc-icon">📡</div>
            </div>
            <div class="card-content">
                <div class="main-text">{{ nfc_data.text }}</div>
                <div class="card-details">
                    {{ nfc_data.tagType }} • {{ nfc_data.manufacturer }}<br>
                    {{ nfc_data.iso }}
                </div>
                <div class="card-serial">{{ nfc_data.serialNumber }}</div>
            </div>
        </div>

        <!-- Controls -->
        <div class="controls">
            <div class="status">
                ✅ NFC Card Ready for Apple Wallet
            </div>

            <button class="add-to-wallet" onclick="addToWallet()">
                <div class="wallet-icon">💳</div>
                Add to Apple Wallet
            </button>

            <div class="alternative-methods">
                <h3>Alternative Methods</h3>
                
                <div class="method">
                    <div class="method-title">QR Code Backup</div>
                    <div class="method-desc">Scan this QR code to get the NFC data</div>
                    <div class="qr-code">
                        <img src="/qr" alt="QR Code" width="120" height="120" />
                    </div>
                </div>

                <div class="method">
                    <div class="method-title">Manual Copy</div>
                    <div class="method-desc">Copy the data to clipboard</div>
                    <button class="btn-secondary" onclick="copyData()">Copy NFC Data</button>
                    <button class="btn-secondary" onclick="downloadJSON()">Download JSON</button>
                </div>
            </div>

            <div class="instructions">
                <strong>How to use:</strong><br>
                1. Click "Add to Apple Wallet" to download the card<br>
                2. Open the downloaded .pkpass file on your iPhone<br>
                3. Add it to your Wallet app<br>
                4. Use the card to share your NFC data
            </div>
        </div>
    </div>

    <script>
        const nfcData = {{ nfc_data_json | safe }};

        function addToWallet() {
            // Download the Apple Wallet pass
            window.location.href = '/wallet/download';
        }

        function copyData() {
            const dataString = `NFC Digital Card
Text: ${nfcData.text}
Type: ${nfcData.tagType}
Serial: ${nfcData.serialNumber}
Payload: ${nfcData.payload_hex}`;

            navigator.clipboard.writeText(dataString).then(() => {
                alert('NFC data copied to clipboard!');
            });
        }

        function downloadJSON() {
            const dataStr = JSON.stringify(nfcData, null, 2);
            const dataBlob = new Blob([dataStr], {type: 'application/json'});
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'nfc_card_data.json';
            link.click();
            URL.revokeObjectURL(url);
        }
    </script>
</body>
</html>
"""

def create_apple_wallet_pass():
    """Create an Apple Wallet pass (.pkpass file) with NFC data"""
    
    # Pass.json structure for Apple Wallet
    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": "pass.com.nfc.digitalcard",
        "serialNumber": NFC_DATA['serialNumber'].replace(':', ''),
        "teamIdentifier": "DEMO123456",  # Demo team ID
        "organizationName": "NFC Digital Cards",
        "description": "NFC Digital Card",
        "logoText": "NFC Card",
        "foregroundColor": "rgb(255, 255, 255)",
        "backgroundColor": "rgb(42, 82, 152)",
        "labelColor": "rgb(255, 255, 255)",
        "generic": {
            "primaryFields": [
                {
                    "key": "nfc-data",
                    "label": "NFC Data",
                    "value": NFC_DATA['text']
                }
            ],
            "secondaryFields": [
                {
                    "key": "tag-type",
                    "label": "Tag Type",
                    "value": NFC_DATA['tagType']
                },
                {
                    "key": "manufacturer",
                    "label": "Manufacturer",
                    "value": NFC_DATA['manufacturer']
                }
            ],
            "auxiliaryFields": [
                {
                    "key": "serial",
                    "label": "Serial Number",
                    "value": NFC_DATA['serialNumber']
                }
            ],
            "backFields": [
                {
                    "key": "payload",
                    "label": "Raw Payload (Hex)",
                    "value": NFC_DATA['payload_hex']
                },
                {
                    "key": "memory",
                    "label": "Memory",
                    "value": f"{NFC_DATA['memorySize']} bytes"
                },
                {
                    "key": "iso",
                    "label": "ISO Standard",
                    "value": NFC_DATA['iso']
                },
                {
                    "key": "atqa-sak",
                    "label": "ATQA/SAK",
                    "value": f"{NFC_DATA['atqa']} / {NFC_DATA['sak']}"
                }
            ]
        },
        "barcode": {
            "message": NFC_DATA['text'],
            "format": "PKBarcodeFormatQR",
            "messageEncoding": "iso-8859-1"
        },
        "nfc": {
            "message": NFC_DATA['text'],
            "encryptionPublicKey": ""  # Would need real encryption key for production
        }
    }
    
    # Create manifest (checksums of all files)
    manifest = {
        "pass.json": hashlib.sha1(json.dumps(pass_json).encode()).hexdigest()
    }
    
    # Create temporary directory for pass files
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Write pass.json
        pass_path = os.path.join(temp_dir, 'pass.json')
        with open(pass_path, 'w') as f:
            json.dump(pass_json, f, indent=2)
        
        # Write manifest.json
        manifest_path = os.path.join(temp_dir, 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Create signature (simplified for demo - real implementation needs certificates)
        signature_path = os.path.join(temp_dir, 'signature')
        with open(signature_path, 'w') as f:
            f.write("DEMO_SIGNATURE_" + str(int(time.time())))
        
        # Create .pkpass file (ZIP archive)
        pkpass_buffer = io.BytesIO()
        with zipfile.ZipFile(pkpass_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(pass_path, 'pass.json')
            zf.write(manifest_path, 'manifest.json')
            zf.write(signature_path, 'signature')
        
        pkpass_buffer.seek(0)
        return pkpass_buffer.getvalue()
        
    finally:
        # Cleanup temp files
        for file in [pass_path, manifest_path, signature_path]:
            if os.path.exists(file):
                os.remove(file)
        os.rmdir(temp_dir)

@app.route('/')
def index():
    """Main page with wallet card preview"""
    return render_template_string(HTML_TEMPLATE, 
                                nfc_data=NFC_DATA, 
                                nfc_data_json=json.dumps(NFC_DATA))

@app.route('/wallet/download')
def download_wallet_pass():
    """Download Apple Wallet pass file"""
    try:
        pkpass_data = create_apple_wallet_pass()
        
        response = Response(
            pkpass_data,
            mimetype='application/vnd.apple.pkpass',
            headers={
                'Content-Disposition': 'attachment; filename="nfc-card.pkpass"',
                'Content-Type': 'application/vnd.apple.pkpass'
            }
        )
        return response
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to create wallet pass',
            'message': str(e),
            'note': 'Demo pass creation - requires Apple Developer certificates for production'
        }), 500

@app.route('/qr')
def generate_qr():
    """Generate QR code for the NFC text data"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=4,
    )
    qr.add_data(NFC_DATA['text'])
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#2a5298", back_color="white")
    
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return Response(img_buffer.getvalue(), mimetype='image/png')

@app.route('/api/nfc')
def api_nfc_data():
    """API endpoint to get full NFC data"""
    response = NFC_DATA.copy()
    response['timestamp'] = datetime.now().isoformat()
    response['status'] = 'active'
    return jsonify(response)

@app.route('/api/wallet/verify')
def verify_wallet_support():
    """Check if device supports Apple Wallet"""
    user_agent = request.headers.get('User-Agent', '')
    is_ios = 'iPhone' in user_agent or 'iPad' in user_agent
    is_safari = 'Safari' in user_agent
    
    return jsonify({
        'supports_wallet': is_ios,
        'is_ios_device': is_ios,
        'is_safari': is_safari,
        'user_agent': user_agent,
        'recommendation': 'Use Safari on iOS for best Wallet experience' if is_ios else 'Apple Wallet not available on this device'
    })

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'NFC Digital Wallet Card',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)