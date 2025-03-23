// Функция для отправки информации о скачивании в наше приложение
async function sendToCleanMaster(url, filename) {
    try {
        const response = await fetch('http://localhost:8080', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: 'download',
                url: url,
                filename: filename
            })
        });
        
        if (!response.ok) {
            console.error('Ошибка при отправке в CleanMaster');
        }
    } catch (error) {
        console.error('Ошибка при отправке в CleanMaster:', error);
    }
}

// Перехватываем запросы на скачивание
chrome.webRequest.onBeforeRequest.addListener(
    function(details) {
        // Проверяем, является ли запрос скачиванием
        if (details.type === 'xmlhttprequest' || details.type === 'main_frame') {
            const url = details.url;
            const filename = url.split('/').pop();
            
            // Отправляем информацию в наше приложение
            sendToCleanMaster(url, filename);
        }
    },
    { urls: ["<all_urls>"] },
    ["blocking"]
);

// Перехватываем события скачивания
chrome.downloads.onDeterminingFilename.addListener(
    function(downloadItem, suggest) {
        // Отправляем информацию о скачивании в наше приложение
        sendToCleanMaster(downloadItem.url, downloadItem.filename);
    }
); 