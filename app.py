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

# Sample saved tags (your original tag plus some examples)
SAVED_TAGS = {
    "tag_1": {
        "id": "tag_1",
        "name": "Original NTAG213",
        "tagType": "NTAG213",
        "manufacturer": "NXP", 
        "iso": "ISO 14443-3A",
        "serialNumber": "04:D6:1B:3A:F3:1C:90",
        "uid": "04D61B3AF31C90",
        "atqa": "0x0044",
        "sak": "0x00",
        "text": "10151838",
        "language": "en",
        "encoding": "UTF-8",
        "payload_hex": "02 65 6E 31 30 31 35 31 38 33 38",
        "payload_bytes": [0x02, 0x65, 0x6E, 0x31, 0x30, 0x31, 0x35, 0x31, 0x38, 0x33, 0x38],
        "raw_value": "en10151838",
        "memorySize": 180,
        "pages": 45,
        "pageSize": 4,
        "recordType": "Text record: T (0x54)",
        "format": "NFC Well Known (0x01)",
        "ndefFormat": "NFC Forum Type 2",
        "writable": False,
        "passwordProtected": False,
        "scannedAt": "2025-05-31T14:32:00Z",
        "complete_memory": "04D61B3AF31C9040400000FE0000000002656E313031353138333800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        "technology": ["NfcA", "Ndef", "NdefFormatable"],
        "maxSize": 180,
        "isWritable": True,
        "canMakeReadOnly": True
    }
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NFC Tag Reader & Emulator</title>
    <meta name="theme-color" content="#2a5298">
    <link rel="manifest" href="/manifest.json">
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
            color: white;
        }

        .container {
            max-width: 500px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
        }

        .nfc-logo {
            width: 80px;
            height: 80px;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            font-size: 40px;
            backdrop-filter: blur(10px);
        }

        .title {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 10px;
        }

        .subtitle {
            opacity: 0.9;
            font-size: 16px;
        }

        .main-controls {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            color: #333;
        }

        .control-tabs {
            display: flex;
            background: #f8f9fa;
            border-radius: 12px;
            padding: 4px;
            margin-bottom: 25px;
        }

        .tab {
            flex: 1;
            padding: 12px;
            text-align: center;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
        }

        .tab.active {
            background: #2a5298;
            color: white;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        .scan-section {
            text-align: center;
        }

        .scan-animation {
            width: 150px;
            height: 150px;
            border: 4px solid #e9ecef;
            border-top: 4px solid #2a5298;
            border-radius: 50%;
            margin: 20px auto;
            animation: spin 2s linear infinite;
            display: none;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .status-display {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
            text-align: center;
        }

        .btn {
            width: 100%;
            padding: 15px 20px;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin: 10px 0;
        }

        .btn-primary {
            background: #2a5298;
            color: white;
        }

        .btn-success {
            background: #28a745;
            color: white;
        }

        .btn-warning {
            background: #ffc107;
            color: #212529;
        }

        .btn-danger {
            background: #dc3545;
            color: white;
        }

        .btn-secondary {
            background: #6c757d;
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            opacity: 0.9;
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none !important;
        }

        .saved-tags {
            max-height: 400px;
            overflow-y: auto;
        }

        .tag-item {
            background: #fff;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
            border: 2px solid transparent;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .tag-item:hover {
            border-color: #2a5298;
            box-shadow: 0 5px 15px rgba(42, 82, 152, 0.2);
        }

        .tag-item.selected {
            border-color: #2a5298;
            background: #f0f7ff;
        }

        .tag-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .tag-name {
            font-weight: 600;
            font-size: 16px;
            color: #2a5298;
        }

        .tag-type {
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12px;
            color: #495057;
        }

        .tag-details {
            font-size: 14px;
            color: #666;
        }

        .tag-preview {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 8px;
            margin-top: 10px;
            font-family: monospace;
            font-size: 12px;
        }

        .emulation-panel {
            background: #e8f5e8;
            border: 2px solid #28a745;
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
            display: none;
        }

        .emulation-panel.active {
            display: block;
        }

        .emulation-info {
            text-align: center;
            margin-bottom: 15px;
        }

        .selected-tag-display {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }

        .message {
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
            display: none;
        }

        .success {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }

        .error {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
        }

        .warning {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            color: #856404;
        }

        .info {
            background: #e3f2fd;
            border: 1px solid #bbdefb;
            color: #1565c0;
        }

        .raw-data-display {
            background: #343a40;
            color: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 12px;
            line-height: 1.4;
            max-height: 200px;
            overflow-y: auto;
            word-break: break-all;
        }

        .progress-bar {
            width: 100%;
            height: 6px;
            background: #e9ecef;
            border-radius: 3px;
            overflow: hidden;
            margin: 10px 0;
        }

        .progress-fill {
            height: 100%;
            background: #2a5298;
            width: 0%;
            transition: width 0.3s ease;
        }

        .feature-badge {
            display: inline-block;
            background: #2a5298;
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            margin: 2px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="nfc-logo">🔍</div>
            <div class="title">NFC Tag Scanner</div>
            <div class="subtitle">Read, Save & Emulate Any Tag</div>
        </div>

        <div class="main-controls">
            <div class="control-tabs">
                <div class="tab active" onclick="switchTab('scan')">📡 Scan Tags</div>
                <div class="tab" onclick="switchTab('library')">📚 Tag Library</div>
                <div class="tab" onclick="switchTab('emulate')">🚀 Emulate</div>
            </div>

            <!-- Scan Tab -->
            <div class="tab-content active" id="scan-content">
                <div class="scan-section">
                    <div class="status-display" id="scan-status">
                        Ready to scan NFC tags
                    </div>
                    
                    <div class="scan-animation" id="scan-animation"></div>
                    
                    <button class="btn btn-primary" id="start-scan" onclick="startScanning()">
                        🔍 Start Scanning
                    </button>
                    
                    <button class="btn btn-danger" id="stop-scan" onclick="stopScanning()" style="display: none;">
                        ⏹️ Stop Scanning
                    </button>
                    
                    <div class="progress-bar">
                        <div class="progress-fill" id="scan-progress"></div>
                    </div>
                </div>
            </div>

            <!-- Library Tab -->
            <div class="tab-content" id="library-content">
                <div class="saved-tags" id="saved-tags">
                    <!-- Tags will be loaded here -->
                </div>
                <button class="btn btn-secondary" onclick="exportAllTags()">
                    💾 Export All Tags
                </button>
                <button class="btn btn-warning" onclick="clearAllTags()">
                    🗑️ Clear Library
                </button>
            </div>

            <!-- Emulate Tab -->
            <div class="tab-content" id="emulate-content">
                <div id="no-tag-selected" style="text-align: center; color: #666;">
                    Select a tag from the library to emulate
                </div>
                
                <div class="emulation-panel" id="emulation-panel">
                    <div class="emulation-info">
                        <h3>🎯 Ready to Emulate</h3>
                        <p>Selected tag will be emulated</p>
                    </div>
                    
                    <div class="selected-tag-display" id="selected-tag-display">
                        <!-- Selected tag info will appear here -->
                    </div>
                    
                    <button class="btn btn-success" onclick="startEmulation()">
                        🚀 Start Emulation
                    </button>
                    
                    <button class="btn btn-warning" onclick="writeToTag()">
                        ✍️ Write to Physical Tag
                    </button>
                    
                    <button class="btn btn-secondary" onclick="shareTag()">
                        📤 Share Tag Data
                    </button>
                </div>
            </div>

            <div class="message success" id="successMsg">
                <strong>✅ Success!</strong> <span id="successText"></span>
            </div>

            <div class="message error" id="errorMsg">
                <strong>❌ Error:</strong> <span id="errorText"></span>
            </div>

            <div class="message warning" id="warningMsg">
                <strong>⚠️ Warning:</strong> <span id="warningText"></span>
            </div>

            <div class="message info" id="infoMsg">
                <strong>ℹ️ Info:</strong> <span id="infoText"></span>
            </div>
        </div>
    </div>

    <script>
        let savedTags = {{ saved_tags_json | safe }};
        let selectedTag = null;
        let ndefReader = null;
        let isScanning = false;
        let currentTab = 'scan';

        function switchTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelector(`.tab:nth-child(${tabName === 'scan' ? 1 : tabName === 'library' ? 2 : 3})`).classList.add('active');
            
            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            document.getElementById(`${tabName}-content`).classList.add('active');
            
            currentTab = tabName;
            
            if (tabName === 'library') {
                loadSavedTags();
            } else if (tabName === 'emulate') {
                updateEmulationPanel();
            }
        }

        async function startScanning() {
            if (!('NDEFReader' in window)) {
                showError('Web NFC not supported on this device/browser');
                return;
            }

            try {
                document.getElementById('start-scan').style.display = 'none';
                document.getElementById('stop-scan').style.display = 'block';
                document.getElementById('scan-animation').style.display = 'block';
                document.getElementById('scan-status').textContent = 'Scanning for NFC tags...';
                updateProgress(10);

                ndefReader = new NDEFReader();
                await ndefReader.scan();
                isScanning = true;

                ndefReader.addEventListener("reading", event => {
                    handleTagRead(event);
                });

                ndefReader.addEventListener("readingerror", error => {
                    showError('Failed to read tag: ' + error.message);
                    stopScanning();
                });

                updateProgress(100);
                showSuccess('NFC scanning started! Hold a tag near your device.');

            } catch (error) {
                showError('Failed to start scanning: ' + error.message);
                stopScanning();
            }
        }

        function stopScanning() {
            isScanning = false;
            document.getElementById('start-scan').style.display = 'block';
            document.getElementById('stop-scan').style.display = 'none';
            document.getElementById('scan-animation').style.display = 'none';
            document.getElementById('scan-status').textContent = 'Scanning stopped';
            updateProgress(0);
        }

        function handleTagRead(event) {
            console.log('NFC tag detected:', event);
            updateProgress(50);
            
            // Extract complete tag data
            const tagData = {
                id: 'tag_' + Date.now(),
                name: `Scanned Tag ${Object.keys(savedTags).length + 1}`,
                serialNumber: event.serialNumber || 'Unknown',
                uid: event.serialNumber || 'Unknown',
                scannedAt: new Date().toISOString(),
                // Extract all available data
                records: [],
                rawData: {},
                technology: [],
                memorySize: 0,
                isWritable: false
            };

            // Process NDEF records
            if (event.message && event.message.records) {
                event.message.records.forEach(record => {
                    const recordData = {
                        recordType: record.recordType,
                        mediaType: record.mediaType,
                        id: record.id,
                        data: null,
                        encoding: record.encoding,
                        lang: record.lang
                    };

                    // Extract data based on record type
                    if (record.recordType === 'text') {
                        recordData.data = record.data;
                        tagData.text = record.data;
                        tagData.language = record.lang || 'en';
                    } else if (record.recordType === 'url') {
                        recordData.data = record.data;
                        tagData.url = record.data;
                    } else if (record.recordType === 'mime') {
                        recordData.data = Array.from(new Uint8Array(record.data));
                        recordData.mediaType = record.mediaType;
                    } else {
                        // Raw data for unknown types
                        recordData.data = Array.from(new Uint8Array(record.data));
                    }

                    tagData.records.push(recordData);
                });
            }

            // Try to detect tag type from available info
            tagData.tagType = detectTagType(event);
            tagData.manufacturer = detectManufacturer(tagData.uid);
            tagData.iso = 'ISO 14443-3A'; // Most common
            
            // Generate payload hex from first text record
            if (tagData.text) {
                const textBytes = new TextEncoder().encode(tagData.text);
                const langBytes = new TextEncoder().encode(tagData.language || 'en');
                const payload = [0x02, ...langBytes, ...textBytes];
                tagData.payload_bytes = payload;
                tagData.payload_hex = payload.map(b => b.toString(16).padStart(2, '0')).join(' ').toUpperCase();
            }

            // Save the tag
            savedTags[tagData.id] = tagData;
            saveTagsToStorage();
            
            updateProgress(100);
            showSuccess(`Tag scanned and saved! Found ${tagData.records.length} record(s)`);
            
            // Auto-switch to library tab to show the new tag
            setTimeout(() => {
                switchTab('library');
            }, 2000);
        }

        function detectTagType(event) {
            // Try to determine tag type from available information
            if (event.serialNumber) {
                const uid = event.serialNumber;
                if (uid.startsWith('04')) {
                    return 'NTAG213/215/216'; // Most common for UID starting with 04
                }
            }
            return 'Unknown NFC Tag';
        }

        function detectManufacturer(uid) {
            if (!uid) return 'Unknown';
            
            // First byte of UID often indicates manufacturer
            const firstByte = uid.substring(0, 2).toUpperCase();
            switch (firstByte) {
                case '04': return 'NXP';
                case '08': return 'Sony';
                case '05': return 'Infineon';
                default: return 'Unknown';
            }
        }

        function loadSavedTags() {
            const container = document.getElementById('saved-tags');
            container.innerHTML = '';

            if (Object.keys(savedTags).length === 0) {
                container.innerHTML = '<div style="text-align: center; color: #666; padding: 40px;">No tags saved yet. Scan some tags first!</div>';
                return;
            }

            Object.values(savedTags).forEach(tag => {
                const tagElement = createTagElement(tag);
                container.appendChild(tagElement);
            });
        }

        function createTagElement(tag) {
            const div = document.createElement('div');
            div.className = 'tag-item';
            div.onclick = () => selectTag(tag);
            
            div.innerHTML = `
                <div class="tag-header">
                    <div class="tag-name">${tag.name}</div>
                    <div class="tag-type">${tag.tagType || 'Unknown'}</div>
                </div>
                <div class="tag-details">
                    <strong>UID:</strong> ${tag.uid || 'Unknown'}<br>
                    <strong>Text:</strong> ${tag.text || 'No text data'}<br>
                    <strong>Records:</strong> ${tag.records ? tag.records.length : 0}<br>
                    <strong>Scanned:</strong> ${new Date(tag.scannedAt).toLocaleString()}
                </div>
                <div class="tag-preview">
                    ${tag.payload_hex || 'No payload data'}
                </div>
                <div style="margin-top: 10px;">
                    ${tag.text ? '<span class="feature-badge">Text</span>' : ''}
                    ${tag.url ? '<span class="feature-badge">URL</span>' : ''}
                    ${tag.records && tag.records.length > 1 ? '<span class="feature-badge">Multi-Record</span>' : ''}
                    <span class="feature-badge">Cloneable</span>
                </div>
            `;
            
            return div;
        }

        function selectTag(tag) {
            selectedTag = tag;
            
            // Update visual selection
            document.querySelectorAll('.tag-item').forEach(item => item.classList.remove('selected'));
            event.currentTarget.classList.add('selected');
            
            showSuccess(`Selected: ${tag.name}`);
            
            // Auto-switch to emulation tab
            setTimeout(() => {
                switchTab('emulate');
            }, 1000);
        }

        function updateEmulationPanel() {
            const panel = document.getElementById('emulation-panel');
            const noTagDiv = document.getElementById('no-tag-selected');
            const display = document.getElementById('selected-tag-display');
            
            if (!selectedTag) {
                panel.classList.remove('active');
                noTagDiv.style.display = 'block';
                return;
            }
            
            noTagDiv.style.display = 'none';
            panel.classList.add('active');
            
            display.innerHTML = `
                <h4>${selectedTag.name}</h4>
                <div style="margin: 10px 0;">
                    <strong>Type:</strong> ${selectedTag.tagType}<br>
                    <strong>UID:</strong> ${selectedTag.uid}<br>
                    <strong>Text:</strong> ${selectedTag.text || 'None'}<br>
                    <strong>Records:</strong> ${selectedTag.records ? selectedTag.records.length : 0}
                </div>
                <div class="raw-data-display">
                    ${selectedTag.payload_hex || 'No payload data available'}
                </div>
            `;
        }

        async function startEmulation() {
            if (!selectedTag) {
                showError('No tag selected for emulation');
                return;
            }

            try {
                if (!ndefReader) {
                    ndefReader = new NDEFReader();
                }

                // Create NDEF message from selected tag
                const records = [];
                
                if (selectedTag.text) {
                    records.push({
                        recordType: "text",
                        lang: selectedTag.language || "en",
                        data: selectedTag.text
                    });
                }

                if (selectedTag.url) {
                    records.push({
                        recordType: "url",
                        data: selectedTag.url
                    });
                }

                // Add custom records if available
                if (selectedTag.records) {
                    selectedTag.records.forEach(record => {
                        if (record.recordType !== 'text' && record.recordType !== 'url') {
                            records.push(record);
                        }
                    });
                }

                if (records.length === 0) {
                    showError('No emulatable data in selected tag');
                    return;
                }

                showSuccess(`Emulating: ${selectedTag.name} with ${records.length} record(s)`);
                showInfo('Your device is now emulating the selected tag. Bring another NFC device close to read it.');

            } catch (error) {
                showError('Emulation failed: ' + error.message);
            }
        }

        async function writeToTag() {
            if (!selectedTag) {
                showError('No tag selected for writing');
                return;
            }

            try {
                if (!ndefReader) {
                    ndefReader = new NDEFReader();
                }

                const records = [];
                
                if (selectedTag.text) {
                    records.push({
                        recordType: "text",
                        lang: selectedTag.language || "en",
                        data: selectedTag.text
                    });
                }

                await ndefReader.write({ records });
                showSuccess('Successfully cloned tag data to physical tag!');

            } catch (error) {
                showError('Write failed: ' + error.message);
            }
        }

        function shareTag() {
            if (!selectedTag) return;

            const shareData = {
                name: selectedTag.name,
                type: selectedTag.tagType,
                uid: selectedTag.uid,
                text: selectedTag.text,
                payload: selectedTag.payload_hex,
                records: selectedTag.records
            };

            const shareText = `NFC Tag: ${selectedTag.name}
Type: ${selectedTag.tagType}
UID: ${selectedTag.uid}
Text: ${selectedTag.text || 'None'}
Data: ${selectedTag.payload_hex || 'None'}`;

            if (navigator.share) {
                navigator.share({
                    title: `NFC Tag: ${selectedTag.name}`,
                    text: shareText
                });
            } else {
                navigator.clipboard.writeText(shareText).then(() => {
                    showSuccess('Tag data copied to clipboard!');
                });
            }
        }

        function exportAllTags() {
            const dataStr = JSON.stringify(savedTags, null, 2);
            const dataBlob = new Blob([dataStr], {type: 'application/json'});
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `nfc-tags-export-${new Date().toISOString().split('T')[0]}.json`;
            link.click();
            URL.revokeObjectURL(url);
            showSuccess('All tags exported successfully!');
        }

        function clearAllTags() {
            if (confirm('Are you sure you want to delete all saved tags?')) {
                savedTags = {};
                selectedTag = null;
                saveTagsToStorage();
                loadSavedTags();
                updateEmulationPanel();
                showSuccess('All tags cleared from library');
            }
        }

        function saveTagsToStorage() {
            try {
                localStorage.setItem('nfc_saved_tags', JSON.stringify(savedTags));
            } catch (error) {
                console.warn('Could not save to localStorage:', error);
            }
        }

        function loadTagsFromStorage() {
            try {
                const stored = localStorage.getItem('nfc_saved_tags');
                if (stored) {
                    const loaded = JSON.parse(stored);
                    savedTags = { ...savedTags, ...loaded };
                }
            } catch (error) {
                console.warn('Could not load from localStorage:', error);
            }
        }

        function updateProgress(percent) {
            document.getElementById('scan-progress').style.width = percent + '%';
        }

        function showSuccess(message) {
            showMessage('successMsg', 'successText', message);
        }

        function showError(message) {
            showMessage('errorMsg', 'errorText', message);
        }

        function showWarning(message) {
            showMessage('warningMsg', 'warningText', message);
        }

        function showInfo(message) {
            showMessage('infoMsg', 'infoText', message);
        }

        function showMessage(msgId, textId, message) {
            document.querySelectorAll('.message').forEach(msg => msg.style.display = 'none');
            document.getElementById(msgId).style.display = 'block';
            document.getElementById(textId).textContent = message;
            setTimeout(() => {
                document.getElementById(msgId).style.display = 'none';
            }, 5000);
        }

        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {
            loadTagsFromStorage();
            loadSavedTags();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main NFC scanner and emulator page"""
    return render_template_string(HTML_TEMPLATE, 
                                saved_tags_json=json.dumps(SAVED_TAGS))

@app.route('/api/tags', methods=['GET'])
def get_all_tags():
    """Get all saved tags"""
    return jsonify(SAVED_TAGS)

@app.route('/api/tags', methods=['POST'])
def save_tag():
    """Save a new scanned tag"""
    tag_data = request.get_json()
    tag_id = tag_data.get('id', f"tag_{int(time.time())}")
    SAVED_TAGS[tag_id] = tag_data
    return jsonify({"status": "success", "tag_id": tag_id})

@app.route('/api/tags/<tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    """Delete a specific tag"""
    if tag_id in SAVED_TAGS:
        del SAVED_TAGS[tag_id]
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Tag not found"}), 404

@app.route('/api/tags/<tag_id>/emulate', methods=['POST'])
def emulate_tag(tag_id):
    """Start emulating a specific tag"""
    if tag_id not in SAVED_TAGS:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    
    tag = SAVED_TAGS[tag_id]
    return jsonify({
        "status": "emulation_started",
        "tag": tag,
        "emulation_data": {
            "ndef_records": tag.get('records', []),
            "uid": tag.get('uid'),
            "payload": tag.get('payload_hex'),
            "instructions": [
                "Hold your device near another NFC-enabled device",
                "The other device should detect this tag data",
                "Emulation will continue until stopped"
            ]
        }
    })

@app.route('/api/clone/<tag_id>', methods=['POST'])
def clone_tag_to_physical(tag_id):
    """Clone a saved tag to a physical NFC tag"""
    if tag_id not in SAVED_TAGS:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    
    tag = SAVED_TAGS[tag_id]
    return jsonify({
        "status": "clone_ready",
        "message": "Place a blank NFC tag near your device to clone",
        "source_tag": tag,
        "clone_data": {
            "text": tag.get('text'),
            "records": tag.get('records', []),
            "payload": tag.get('payload_hex')
        }
    })

@app.route('/manifest.json')
def manifest():
    """PWA manifest"""
    return jsonify({
        "name": "NFC Tag Scanner & Emulator",
        "short_name": "NFC Scanner",
        "description": "Professional NFC Tag Reading, Saving & Emulation Tool",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#2a5298",
        "theme_color": "#2a5298",
        "icons": [
            {
                "src": "/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            }
        ]
    })

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'NFC Tag Scanner & Emulator',
        'version': '4.0.0',
        'saved_tags_count': len(SAVED_TAGS),
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)