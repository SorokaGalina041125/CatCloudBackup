"""
Программа для резервного копирования картинок кошек с сайта cataas.com в Яндекс.Диск.
"""
import json
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class CatCloudBackup:
    """Класс для резервного копирования картинок кошек в Яндекс.Диск."""
    
    YANDEX_API_BASE_URL = "https://cloud-api.yandex.net/v1/disk"
    CAT_API_BASE_URL = "https://cataas.com/cat/says"
    REQUEST_TIMEOUT = 30
    
    def __init__(self, yandex_token: str, group_name: str = "Нетология") -> None:
        """
        Инициализация класса.
        
        Args:
            yandex_token: OAuth токен для Яндекс.Диска
            group_name: Название группы в Нетологии (используется как имя папки)
        """
        self._yandex_token = yandex_token
        self._group_name = group_name
        self._uploaded_files_info = []
    
    def _get_authorization_headers(self) -> dict:
        """Возвращает заголовки с авторизацией для запросов к Яндекс.Диску."""
        return {"Authorization": f"OAuth {self._yandex_token}"}
    
    def _download_cat_image(self, text: str) -> bytes:
        """
        Загружает картинку кота с текстом с сайта cataas.com.
        
        Args:
            text: Текст для картинки
            
        Returns:
            Бинарные данные изображения
            
        Raises:
            requests.exceptions.RequestException: При ошибке запроса
        """
        url = f"{self.CAT_API_BASE_URL}/{text}"
        try:
            response = requests.get(url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.content
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException(
                f"Таймаут при загрузке изображения с {url}"
            )
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Ошибка при загрузке изображения: {e}"
            )
    
    def _create_remote_directory(self, directory_path: str) -> None:
        """
        Создает папку на Яндекс.Диске.
        
        Args:
            directory_path: Путь к папке
            
        Raises:
            requests.exceptions.RequestException: При ошибке запроса
        """
        headers = self._get_authorization_headers()
        url = f"{self.YANDEX_API_BASE_URL}/resources"
        params = {"path": directory_path}
        
        try:
            response = requests.put(
                url, 
                headers=headers, 
                params=params, 
                timeout=self.REQUEST_TIMEOUT
            )
            
            # Папка уже существует - это нормально
            if response.status_code == 409:
                return
            
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Ошибка при создании папки {directory_path}: {e}"
            )
    
    def _generate_filename(self, text: str) -> str:
        """
        Генерирует уникальное имя файла из текста с временной меткой.
        
        Args:
            text: Исходный текст
            
        Returns:
            Уникальное имя файла с расширением .jpg
        """
        # Заменяем небезопасные символы
        forbidden_chars = " /\\:*?\"<>|"
        filename = text
        for char in forbidden_chars:
            filename = filename.replace(char, "_")
        
        # Добавляем временную метку с миллисекундами для уникальности
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return f"{filename}_{timestamp}.jpg"
    
    def _get_upload_url(self, remote_path: str) -> str:
        """
        Получает URL для загрузки файла на Яндекс.Диск.
        
        Args:
            remote_path: Путь к файлу на Яндекс.Диске
            
        Returns:
            URL для загрузки файла
        """
        headers = self._get_authorization_headers()
        url = f"{self.YANDEX_API_BASE_URL}/resources/upload"
        params = {"path": remote_path, "overwrite": "true"}
        
        try:
            response = requests.get(
                url, 
                headers=headers, 
                params=params, 
                timeout=self.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()["href"]
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Ошибка при получении URL для загрузки: {e}"
            )
    
    def _get_file_metadata(self, remote_path: str) -> dict:
        """
        Получает метаданные файла с Яндекс.Диска.
        
        Args:
            remote_path: Путь к файлу на Яндекс.Диске
            
        Returns:
            Словарь с метаданными файла
        """
        headers = self._get_authorization_headers()
        url = f"{self.YANDEX_API_BASE_URL}/resources"
        params = {"path": remote_path}
        
        try:
            response = requests.get(
                url, 
                headers=headers, 
                params=params, 
                timeout=self.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Ошибка при получении метаданных файла: {e}"
            )
    
    def _wait_for_operation_completion(self, operation_url: str) -> None:
        """
        Ожидает завершения асинхронной операции на Яндекс.Диске.
        
        Args:
            operation_url: URL для проверки статуса операции
            
        Raises:
            requests.exceptions.RequestException: При ошибке или неудаче операции
        """
        headers = self._get_authorization_headers()
        max_attempts = 10
        delay_seconds = 1
        
        for attempt in range(max_attempts):
            try:
                response = requests.get(
                    operation_url, 
                    headers=headers, 
                    timeout=self.REQUEST_TIMEOUT
                )
                response.raise_for_status()
                operation_status = response.json()
                
                if operation_status.get("status") == "success":
                    return
                elif operation_status.get("status") == "failed":
                    error_msg = operation_status.get("message", "Неизвестная ошибка")
                    raise requests.exceptions.RequestException(
                        f"Ошибка при загрузке файла: {error_msg}"
                    )
                elif operation_status.get("status") == "in-progress":
                    if attempt < max_attempts - 1:
                        time.sleep(delay_seconds)
                        delay_seconds *= 2  # exponential backoff
                    continue
                    
            except requests.exceptions.RequestException as e:
                if attempt == max_attempts - 1:
                    raise requests.exceptions.RequestException(
                        f"Не удалось завершить операцию после {max_attempts} попыток: {e}"
                    )
    
    def _upload_file_to_disk(self, file_data: bytes, filename: str) -> dict:
        """
        Загружает файл на Яндекс.Диск с проверкой статуса операции.
        
        Args:
            file_data: Бинарные данные файла
            filename: Имя файла
            
        Returns:
            Информация о загруженном файле
        """
        remote_path = f"/{self._group_name}/{filename}"
        
        try:
            # Получаем URL для загрузки
            upload_url = self._get_upload_url(remote_path)
            
            # Загружаем файл
            response = requests.put(upload_url, data=file_data, timeout=60)
            response.raise_for_status()
            
            # Проверяем, не является ли ответ асинхронной операцией (статус 202)
            if response.status_code == 202:
                operation_url = response.json().get("href")
                if operation_url:
                    print("⏳ Файл принят в обработку. Ожидаю завершения загрузки...")
                    self._wait_for_operation_completion(operation_url)
            
            # Получаем информацию о файле
            file_metadata = self._get_file_metadata(remote_path)
            
            return {
                "name": filename,
                "path": remote_path,
                "size": file_metadata.get("size", len(file_data)),
                "created": file_metadata.get("created", datetime.now().isoformat()),
                "modified": file_metadata.get("modified", datetime.now().isoformat())
            }
            
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException(
                f"Таймаут при загрузке файла {filename}"
            )
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Ошибка при загрузке файла {filename}: {e}"
            )
    
    def backup_cat_image(self, text: str) -> dict:
        """
        Выполняет резервное копирование картинки кота.
        
        Args:
            text: Текст для картинки
            
        Returns:
            Информация о загруженном файле
        """
        # Создаем папку если её нет
        self._create_remote_directory(f"/{self._group_name}")
        
        # Получаем картинку
        image_data = self._download_cat_image(text)
        
        # Формируем уникальное имя файла
        filename = self._generate_filename(text)
        
        # Загружаем на Яндекс.Диск
        file_info = self._upload_file_to_disk(image_data, filename)
        
        # Сохраняем информацию о файле
        self._uploaded_files_info.append(file_info)
        
        return file_info
    
    def save_backup_info(self, filename: str = "backup_info.json") -> None:
        """
        Сохраняет информацию о загруженных файлах в JSON файл.
        
        Args:
            filename: Имя JSON файла
        """
        backup_data = {
            "group_name": self._group_name,
            "backup_date": datetime.now().isoformat(),
            "files": self._uploaded_files_info,
            "total_files": len(self._uploaded_files_info),
            "total_size": sum(file_info["size"] for file_info in self._uploaded_files_info)
        }
        
        try:
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(backup_data, file, ensure_ascii=False, indent=2)
        except (IOError, OSError) as e:
            raise Exception(f"Ошибка при сохранении файла {filename}: {e}")


def _get_yandex_token() -> str:
    """
    Получает токен Яндекс.Диска из переменных окружения или от пользователя.
    
    Returns:
        OAuth токен Яндекс.Диска
    """
    yandex_token = os.getenv("YANDEX_TOKEN")
    if not yandex_token:
        yandex_token = input("Введите OAuth токен Яндекс.Диска: ").strip()
    return yandex_token


def _get_group_name() -> str:
    """
    Получает название группы из переменных окружения.
    
    Returns:
        Название группы
    """
    return os.getenv("GROUP_NAME", "Нетология")


def _get_text_from_user() -> str:
    """
    Запрашивает текст для картинки у пользователя.
    
    Returns:
        Текст для картинки
        
    Raises:
        ValueError: Если текст пустой
    """
    text = input("Введите текст для картинки кота: ").strip()
    if not text:
        raise ValueError("Текст не может быть пустым!")
    return text


def _print_error_details(error: requests.exceptions.RequestException) -> None:
    """
    Выводит детали ошибки при запросе.
    
    Args:
        error: Исключение, возникшее при запросе
    """
    print(f"  Статус код: {error.response.status_code}")
    
    try:
        error_json = error.response.json()
        if "message" in error_json:
            print(f"  Сообщение: {error_json['message']}")
        else:
            print(f"  Ответ: {error.response.text[:200]}...")
    except (json.JSONDecodeError, AttributeError):
        print(f"  Ответ: {error.response.text[:200] if hasattr(error.response, 'text') else 'Нет деталей'}...")


def _print_success_message(file_info: dict) -> None:
    """
    Выводит сообщение об успешной загрузке.
    
    Args:
        file_info: Информация о загруженном файле
    """
    print("✅ Картинка успешно загружена!")
    print(f"  📄 Имя файла: {file_info['name']}")
    print(f"  📊 Размер: {file_info['size']} байт")
    print(f"  📂 Путь на Яндекс.Диске: {file_info['path']}")


def _print_program_header() -> None:
    """Выводит заголовок программы."""
    separator = "=" * 50
    print(f"{separator}")
    print("CatCloudBackup - Резервное копирование картинок кошек")
    print(f"{separator}")


def _print_program_footer() -> None:
    """Выводит завершающее сообщение программы."""
    separator = "=" * 50
    print(f"\n{separator}")
    print("🎉 Резервное копирование завершено успешно!")
    print("🔗 Проверить Яндекс.Диск: https://disk.yandex.ru/client/disk")
    print(f"{separator}")


def main() -> None:
    """Основная функция программы."""
    _print_program_header()
    
    try:
        # Получаем необходимые данные
        yandex_token = _get_yandex_token()
        group_name = _get_group_name()
        print(f"📁 Название группы (папки): {group_name}")
        
        text = _get_text_from_user()
        
        # Создаем экземпляр класса и выполняем резервное копирование
        backup = CatCloudBackup(yandex_token, group_name)
        
        print(f"\n🐱 Получаю картинку кота с текстом '{text}'...")
        file_info = backup.backup_cat_image(text)
        
        _print_success_message(file_info)
        
        # Сохраняем информацию в JSON
        print("\n💾 Сохраняю информацию о загруженных файлах...")
        backup.save_backup_info()
        print("✅ Информация сохранена в backup_info.json")
        
        _print_program_footer()
        
    except ValueError as error:
        print(f"❌ Ошибка: {error}")
    except requests.exceptions.RequestException as error:
        print(f"\n❌ Ошибка при работе с API: {error}")
        if hasattr(error, 'response') and error.response is not None:
            _print_error_details(error)
    except Exception as error:
        print(f"\n❌ Произошла непредвиденная ошибка: {error}")
        print("Пожалуйста, проверьте подключение к интернету и правильность токена.")


if __name__ == "__main__":
    main()