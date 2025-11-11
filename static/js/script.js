document.addEventListener('DOMContentLoaded', function() {
    // Fetch and update records every 5 seconds
    function updateRecords() {
        fetch('/get_records')
            .then(response => response.json())
            .then(data => {
                const tableBody = document.getElementById('records-body');
                tableBody.innerHTML = '';
                
                data.forEach(record => {
                    const row = document.createElement('tr');
                    
                    // Format employee status with class
                    const employeeClass = record.employee === 'Yes' ? 'employee-yes' : 'employee-no';
                    
                    row.innerHTML = `
                        <td>${record.vehicle_number || 'N/A'}</td>
                        <td>${record.camera || 'N/A'}</td>
                        <td>${formatToIST(record.entry_time) || 'N/A'}</td>
                        <td>${formatToIST(record.exit_time) || 'N/A'}</td>
                        <td class="${employeeClass}">${record.employee || 'N/A'}</td>
                    `;
                    tableBody.appendChild(row);
                });
            })
            .catch(error => console.error('Error fetching records:', error));
    }
    
    // Format time to IST (UTC+5:30)
    function formatToIST(timeString) {
        if (timeString === 'N/A' || !timeString) return 'N/A';
        
        try {
            // Handle different time string formats
            let date;
            if (timeString.includes('T')) {
                // ISO format
                date = new Date(timeString);
            } else if (timeString.includes('Z')) {
                // UTC format
                date = new Date(timeString);
            } else {
                // Try to parse other formats
                date = new Date(timeString);
            }
            
            // Check if date is valid
            if (isNaN(date.getTime())) return timeString;
            
            // Format to IST (India Standard Time)
            // Using toLocaleString with timeZone option
            return date.toLocaleString('en-IN', {
                timeZone: 'Asia/Kolkata',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            }).replace(/\//g, '-');
        } catch (e) {
            console.error('Error formatting time to IST:', e);
            return timeString;
        }
    }
    
    // Initial load and periodic updates
    updateRecords();
    setInterval(updateRecords, 5000);
    
    // Camera status simulation (in real app, check actual connection)
    function updateCameraStatus() {
        const entryStatus = document.getElementById('entry-status');
        const exitStatus = document.getElementById('exit-status');
        
        // Simulate occasional disconnections for demo
        const statuses = ['online', 'offline'];
        const randomStatus = statuses[Math.floor(Math.random() * statuses.length)];
        
        entryStatus.className = `status ${randomStatus === 'online' ? 'online' : 'offline'}`;
        entryStatus.textContent = `Entry Camera: ${randomStatus === 'online' ? 'Online' : 'Offline'}`;
        
        exitStatus.className = `status ${randomStatus === 'online' ? 'online' : 'offline'}`;
        exitStatus.textContent = `Exit Camera: ${randomStatus === 'online' ? 'Online' : 'Offline'}`;
    }
    
    // Update status every 10 seconds
    updateCameraStatus();
    setInterval(updateCameraStatus, 10000);
});