#!/usr/bin/env python3
"""
Скрипт для нагрузочного тестирования Quart приложения
Загружает /sign_all, извлекает ссылки на транзакции и тестирует их параллельно
"""

import asyncio
import aiohttp
import time
import re
from urllib.parse import urljoin
from collections import defaultdict
import sys

BASE_URL = "http://127.0.0.1:8000"
CONCURRENT_REQUESTS = 10  # Количество параллельных запросов
REPEAT_COUNT = 5  # Сколько раз повторить каждую ссылку


async def fetch_page(session, url, timeout=30):
    """Загружает страницу и возвращает содержимое и время загрузки"""
    start_time = time.time()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            content = await response.text()
            load_time = time.time() - start_time
            return {
                'url': url,
                'status': response.status,
                'content': content,
                'load_time': load_time,
                'size': len(content)
            }
    except Exception as e:
        load_time = time.time() - start_time
        return {
            'url': url,
            'status': 'ERROR',
            'content': '',
            'load_time': load_time,
            'size': 0,
            'error': str(e)
        }


async def fetch_page_with_resources(session, url):
    """Загружает страницу и все её ресурсы (CSS, JS, картинки)"""
    page_result = await fetch_page(session, url)
    
    if page_result['status'] != 200:
        return [page_result]
    
    # Извлекаем ссылки на ресурсы
    content = page_result['content']
    resource_urls = []
    
    # CSS файлы
    css_links = re.findall(r'href="([^"]+\.css[^"]*)"', content)
    resource_urls.extend([urljoin(url, link) for link in css_links])
    
    # JS файлы
    js_links = re.findall(r'src="([^"]+\.js[^"]*)"', content)
    resource_urls.extend([urljoin(url, link) for link in js_links])
    
    # Картинки
    img_links = re.findall(r'src="([^"]+\.(png|jpg|jpeg|gif|svg|ico)[^"]*)"', content)
    resource_urls.extend([urljoin(url, link[0]) for link in img_links])
    
    # Удаляем дубликаты и внешние ссылки
    resource_urls = list(set([url for url in resource_urls if url.startswith(BASE_URL)]))
    
    # Загружаем ресурсы параллельно
    resource_tasks = [fetch_page(session, resource_url, timeout=10) for resource_url in resource_urls]
    resource_results = await asyncio.gather(*resource_tasks, return_exceptions=True)
    
    # Обрабатываем исключения
    processed_results = [page_result]
    for result in resource_results:
        if isinstance(result, Exception):
            processed_results.append({
                'url': 'unknown',
                'status': 'EXCEPTION',
                'content': '',
                'load_time': 0,
                'size': 0,
                'error': str(result)
            })
        else:
            processed_results.append(result)
    
    return processed_results


async def extract_transaction_links(session):
    """Извлекает ссылки на транзакции из страницы /sign_all"""
    print("Загружаем /sign_all для извлечения ссылок на транзакции...")
    
    sign_all_url = f"{BASE_URL}/sign_all"
    result = await fetch_page(session, sign_all_url)
    
    if result['status'] != 200:
        print(f"Ошибка загрузки /sign_all: {result.get('error', 'Unknown error')}")
        return []
    
    # Извлекаем ссылки на транзакции
    content = result['content']
    pattern = r'href="(/sign_tools/[a-f0-9]{64})"'
    matches = re.findall(pattern, content)
    
    transaction_urls = [f"{BASE_URL}{match}" for match in matches]
    unique_urls = list(set(transaction_urls))
    
    print(f"Найдено {len(unique_urls)} уникальных транзакций")
    return unique_urls


async def test_single_url(session, url, repeat_count):
    """Тестирует одну URL несколько раз с загрузкой всех ресурсов"""
    results = []
    
    for i in range(repeat_count):
        print(f"  Тест {i+1}/{repeat_count} для {url}")
        page_results = await fetch_page_with_resources(session, url)
        results.extend(page_results)
    
    return results


async def run_load_test():
    """Основная функция нагрузочного тестирования"""
    print(f"Запуск нагрузочного тестирования для {BASE_URL}")
    print(f"Параллельные запросы: {CONCURRENT_REQUESTS}")
    print(f"Повторений для каждой URL: {REPEAT_COUNT}")
    print("-" * 50)
    
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Извлекаем ссылки на транзакции
        transaction_urls = await extract_transaction_links(session)
        
        if not transaction_urls:
            print("Не найдено ссылок для тестирования")
            return
        
        # Ограничиваем количество URL для теста (чтобы не перегрузить)
        test_urls = transaction_urls[:50]  # Берем первые 5 транзакций
        
        print(f"Тестируем {len(test_urls)} транзакций:")
        for url in test_urls:
            print(f"  - {url}")
        print("-" * 50)
        
        # Запускаем тесты параллельно
        start_time = time.time()
        
        # Создаем семафор для ограничения параллельных запросов
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
        
        async def test_with_semaphore(url):
            async with semaphore:
                return await test_single_url(session, url, REPEAT_COUNT)
        
        # Запускаем все тесты параллельно
        all_tasks = [test_with_semaphore(url) for url in test_urls]
        all_results = await asyncio.gather(*all_tasks)
        
        total_time = time.time() - start_time
        
        # Обрабатываем результаты
        all_requests = []
        for url_results in all_results:
            all_requests.extend(url_results)
        
        # Статистика
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТЫ НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ")
        print("=" * 60)
        
        total_requests = len(all_requests)
        successful_requests = len([r for r in all_requests if r['status'] == 200])
        error_requests = len([r for r in all_requests if r['status'] != 200])
        
        load_times = [r['load_time'] for r in all_requests if r['status'] == 200]
        total_size = sum(r['size'] for r in all_requests if r['status'] == 200)
        
        print(f"Общее время тестирования: {total_time:.2f} секунд")
        print(f"Всего запросов: {total_requests}")
        print(f"Успешных запросов: {successful_requests}")
        print(f"Ошибок: {error_requests}")
        print(f"Процент успешных: {(successful_requests/total_requests*100):.1f}%")
        
        if load_times:
            print(f"\nВремя отклика:")
            print(f"  Минимальное: {min(load_times):.3f}s")
            print(f"  Максимальное: {max(load_times):.3f}s")
            print(f"  Среднее: {sum(load_times)/len(load_times):.3f}s")
            
            load_times.sort()
            p50 = load_times[len(load_times)//2]
            p95 = load_times[int(len(load_times)*0.95)]
            print(f"  Медиана (p50): {p50:.3f}s")
            print(f"  95-й процентиль: {p95:.3f}s")
        
        print(f"\nОбъем данных: {total_size/1024:.1f} KB")
        print(f"Средняя скорость: {total_requests/total_time:.1f} запросов/сек")
        
        # Статистика по типам ресурсов
        resource_stats = defaultdict(list)
        for r in all_requests:
            if r['status'] == 200:
                url = r['url']
                if '/sign_tools/' in url:
                    resource_stats['HTML pages'].append(r['load_time'])
                elif '.css' in url:
                    resource_stats['CSS files'].append(r['load_time'])
                elif '.js' in url:
                    resource_stats['JS files'].append(r['load_time'])
                elif any(ext in url for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico']):
                    resource_stats['Images'].append(r['load_time'])
                else:
                    resource_stats['Other'].append(r['load_time'])
        
        print(f"\nСтатистика по типам ресурсов:")
        for resource_type, times in resource_stats.items():
            if times:
                avg_time = sum(times) / len(times)
                print(f"  {resource_type}: {len(times)} запросов, среднее время {avg_time:.3f}s")
        
        # Показываем ошибки
        if error_requests > 0:
            print(f"\nОшибки:")
            error_counts = defaultdict(int)
            for r in all_requests:
                if r['status'] != 200:
                    error_key = f"{r['status']} - {r.get('error', 'Unknown')}"
                    error_counts[error_key] += 1
            
            for error, count in error_counts.items():
                print(f"  {error}: {count} раз")


if __name__ == "__main__":
    print("Нагрузочное тестирование Quart приложения")
    print("Убедитесь, что приложение запущено на http://127.0.0.1:8000")
    print()
    
    try:
        asyncio.run(run_load_test())
    except KeyboardInterrupt:
        print("\nТестирование прервано пользователем")
    except Exception as e:
        print(f"\nОшибка при тестировании: {e}")
        sys.exit(1)
