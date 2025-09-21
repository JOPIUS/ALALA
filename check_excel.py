import pandas as pd

# Проверяем последний Excel файл
file_path = r'C:\ManekiNeko\AVITO_API\output\21092025_Выгрузка_АМО_45_14.xlsx'

print(f"Проверяем файл: {file_path}")

# Читаем все листы
xl = pd.ExcelFile(file_path)
print('Листы:', xl.sheet_names)

# Проверяем лист "paid_cvs" на наличие новых колонок
df = pd.read_excel(file_path, sheet_name='paid_cvs')
print(f'\nЛист "paid_cvs": {df.shape[0]} строк, {df.shape[1]} колонок')

if not df.empty:
    print('\nКолонки в файле:')
    for i, col in enumerate(df.columns, 1):
        print(f'  {i}. {col}')
    
    # Проверяем статусы
    if 'job_search_status_web' in df.columns:
        print(f'\n📋 Статусы поиска работы:')
        status_counts = df['job_search_status_web'].value_counts(dropna=False)
        print(status_counts if not status_counts.empty else "Все значения пустые")
    
    if 'ready_to_start_web' in df.columns:
        print(f'\n⏱️ Готовность к началу работы:')
        ready_counts = df['ready_to_start_web'].value_counts(dropna=False)
        print(ready_counts if not ready_counts.empty else "Все значения пустые")
    
    # Показываем примеры кандидатов
    print(f'\n👤 Примеры кандидатов:')
    display_cols = ['candidate_name_web', 'job_search_status_web', 'ready_to_start_web', 'city_web']
    available_cols = [col for col in display_cols if col in df.columns]
    print(df[available_cols].head(3).to_string(index=False))
else:
    print("⚠️ DataFrame пустой")