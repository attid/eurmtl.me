let translations = {};

async function loadLanguage(lang) {
    const response = await fetch(`/static/lang/${lang}.json`);
    translations = await response.json();
    updateTextContent();
}

function updateTextContent() {
    document.querySelectorAll('[data-translate]').forEach(element => {
        const key = element.getAttribute('data-translate');
        if (translations[key]) {
            element.innerHTML = translations[key];
        }
    });
    document.querySelectorAll('[data-translate-placeholder]').forEach(element => {
        const key = element.getAttribute('data-translate-placeholder');
        if (translations[key]) {
            element.placeholder = translations[key];
        }
    });
}

// Установить язык и сохранить в Local Storage
function setLanguage(lang) {
    localStorage.setItem('preferredLanguage', lang);
    loadLanguage(lang);
    updateButtonStyles(lang);
}

function updateButtonStyles(lang) {
    const enButton = document.getElementById('lang-en');
    const ruButton = document.getElementById('lang-ru');

    if (lang === 'en') {
        enButton.classList.add('is-primary');
        ruButton.classList.remove('is-primary');
    } else {
        ruButton.classList.add('is-primary');
        enButton.classList.remove('is-primary');
    }
}

// Определение языка пользователя и загрузка предпочтительного языка
function detectUserLanguage() {
    const savedLanguage = localStorage.getItem('preferredLanguage');
    if (savedLanguage) {
        return savedLanguage;
    }
    const userLang = navigator.language || navigator.userLanguage;
    return userLang.startsWith('ru') ? 'ru' : 'en';
}

// Загрузка языка на основании настроек браузера или предпочтительного языка
const userLanguage = detectUserLanguage();
loadLanguage(userLanguage);
updateButtonStyles(userLanguage);
