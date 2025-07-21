document.getElementById('csv-upload-form').onsubmit = function(e) {
    e.preventDefault();
    let formData = new FormData(this);
    let xhr = new XMLHttpRequest();
    xhr.open('POST', '', true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
            document.getElementById('progress-bar').style.display = 'block';
            document.getElementById('progress').value = (e.loaded / e.total) * 100;
        }
    };
    xhr.onload = function() {
        if (xhr.status === 200) {
            let data = JSON.parse(xhr.responseText);
            showPreview(data.rows);
        }
    };
    xhr.send(formData);
};

function showPreview(rows) {
    let previewDiv = document.getElementById('preview');
    let html = '<table border="1">';
    rows.slice(0, 6).forEach(row => {
        html += '<tr>' + row.map(cell => `<td>${cell}</td>`).join('') + '</tr>';
    });
    html += '</table>';
    previewDiv.innerHTML = html;

    // Mapping dropdowns
    let mappingDiv = document.getElementById('mapping');
    let headers = rows[0];
    let modelFields = ['kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size'];
    let mappingHtml = '<h4>Map CSV Columns to Fields</h4><form id="mapping-form">';
    headers.forEach((header, idx) => {
        mappingHtml += `<label>${header}: <select name="col${idx}">`;
        mappingHtml += '<option value="">--Ignore--</option>';
        modelFields.forEach(field => {
            mappingHtml += `<option value="${field}">${field}</option>`;
        });
        mappingHtml += '</select></label><br>';
    });
    mappingHtml += '<button type="button" onclick="submitMappedData()">Upload Data</button></form>';
    mappingDiv.innerHTML = mappingHtml;

    window.csvRows = rows;
}

function submitMappedData() {
    let form = document.getElementById('mapping-form');
    let mapping = {};
    let selects = form.querySelectorAll('select');
    let usedFields = new Set();
    for (let i = 0; i < selects.length; i++) {
        let val = selects[i].value;
        if (val) {
            if (usedFields.has(val)) {
                document.getElementById('validation-errors').innerText = 'Duplicate field mapping: ' + val;
                return;
            }
            usedFields.add(val);
            mapping[i] = val;
        }
    }
    if (!Object.values(mapping).includes('kitta_number') || !Object.values(mapping).includes('lat') || !Object.values(mapping).includes('lon')) {
        document.getElementById('validation-errors').innerText = 'kitta_number, lat, and lon fields are required.';
        return;
    }
    fetch('', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify({
            action: 'save',
            mapping: mapping,
            rows: window.csvRows
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('validation-errors').innerText = '';
            alert('Upload successful!');
            loadUploadHistory();
        } else {
            document.getElementById('validation-errors').innerText = data.error || 'Upload failed.';
        }
    });
}

function loadUploadHistory() {
    fetch('', {headers: {'X-Requested-With': 'XMLHttpRequest'}})
    .then(response => response.json())
    .then(data => {
        let html = '<h4>Upload History</h4><table border="1"><tr><th>File</th><th>Time</th><th>Status</th><th>Error</th></tr>';
        data.history.forEach(h => {
            html += `<tr>
                <td>${h.filename}</td>
                <td>${h.upload_time}</td>
                <td>${h.status}</td>
                <td>${h.error_message || ''}</td>
            </tr>`;
        });
        html += '</table>';
        document.getElementById('upload-history').innerHTML = html;
    });
}
window.onload = loadUploadHistory; 