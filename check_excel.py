import pandas as pd

# Проверяем последний Excel файл v11
file_path = r'C:\ManekiNeko\AVITO_API\output\21092025_Выгрузка_АМО_05_52.xlsx'

print(f"Проверяем файл v11: {file_path}")

# Читаем все листы
xl = pd.ExcelFile(file_path)
print('Листы:', xl.sheet_names)

# Проверяем лист "paid_cvs" на наличие новых колонок v11
df = pd.read_excel(file_path, sheet_name='paid_cvs')
print(f'\nЛист "paid_cvs": {df.shape[0]} строк, {df.shape[1]} колонок')

if not df.empty:
    print('\nКолонки в файле v11:')
    for i, col in enumerate(df.columns, 1):
        print(f'  {i}. {col}')
    
    # Проверяем новые статусы v11
    new_v11_columns = ['chat_status', 'interest_level', 'last_message_direction', 'last_message_text']
    
    for col in new_v11_columns:
        if col in df.columns:
            print(f'\n� {col.upper()}:')
            status_counts = df[col].value_counts(dropna=False)
            print(status_counts if not status_counts.empty else "Все значения пустые")
    
    # Проверяем статусы v10
    v10_columns = ['job_search_status_web', 'ready_to_start_web']
    for col in v10_columns:
        if col in df.columns:
            print(f'\n🔍 {col.upper()}:')
            status_counts = df[col].value_counts(dropna=False)
            print(status_counts if not status_counts.empty else "Все значения пустые")
    
    # Показываем примеры кандидатов с новыми полями
    print(f'\n👤 Примеры кандидатов v11:')
    display_cols = ['candidate_name_web', 'chat_status', 'interest_level', 'job_search_status_web', 'ready_to_start_web']
    available_cols = [col for col in display_cols if col in df.columns]
    if available_cols:
        print(df[available_cols].head(2).to_string(index=False))
else:
    print("⚠️ DataFrame пустой")