function showToast(message, type = 'success') {
  const toastContainer = document.getElementById('toast-container');

  // Создаем элемент тоста
  const toastElement = document.createElement('div');
  toastElement.className = `toast align-items-center text-bg-${type} border-0 mb-3`;
  toastElement.setAttribute('role', 'alert');
  toastElement.setAttribute('aria-live', 'assertive');
  toastElement.setAttribute('aria-atomic', 'true');
  toastElement.setAttribute('data-bs-autohide', 'true');
  //toastElement.setAttribute('data-bs-delay', '15000'); // 15 секунд

  // Добавляем внутреннюю структуру тоста
  toastElement.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">
        ${message}
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  `;

  // Добавляем тост в контейнер
  toastContainer.appendChild(toastElement);

  // Инициализируем и показываем тост
  const toast = new bootstrap.Toast(toastElement);
  toast.show();

  // Удаляем тост после скрытия
  toastElement.addEventListener('hidden.bs.toast', function() {
    toastElement.remove();
  });
}
