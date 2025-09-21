// Тестируем регулярные выражения для статусов
const testTexts = [
    "Активно ищу работу, готов выйти завтра",
    "ищу работу в IT сфере", 
    "Готов к работе, активен",
    "могу приступить завтра к обязанностям",
    "Активно ищет работу в области",
    "готов начать сегодня работать",
    "ищет работу активно",
    "готов выйти на работу немедленно",
    "Активно ищу работу, рассматриваю предложения",
    "готов приступить сразу",
    "начну работать завтра"
];

// Текущие регулярки
const jobSearchRegex = /(активно\s+ищ[уы]\s+работу|ищ[уы]\s+работу|активен|готов\s+к\s+работе)/i;
const readyToStartRegex = /(готов\s+выйти\s+(?:завтра|сегодня|немедленно|сразу)|готов\s+(?:завтра|сегодня|сразу)|могу\s+приступить\s+(?:завтра|сегодня|сразу)|начн[уы]\s+(?:завтра|сегодня|сразу))/i;

console.log("=== Тестирование регулярных выражений ===");

testTexts.forEach((text, i) => {
    console.log(`\n${i+1}. "${text}"`);
    
    const jobMatch = text.match(jobSearchRegex);
    const readyMatch = text.match(readyToStartRegex);
    
    if (jobMatch) {
        console.log(`   🔍 Поиск работы: "${jobMatch[0]}"`);
    }
    
    if (readyMatch) {
        console.log(`   ⏱️ Готовность: "${readyMatch[0]}"`);
    }
    
    if (!jobMatch && !readyMatch) {
        console.log(`   ❌ Ничего не найдено`);
    }
});

// Улучшенные регулярки
console.log("\n\n=== Тестирование улучшенных регулярок ===");

const improvedJobSearchRegex = /(активно\s+ищ[ауеыу]|ищ[ауеыу]\s+работу|активен|готов\s+к\s+работе|рассматриваю\s+предложения)/i;
const improvedReadyRegex = /(готов\s+(?:выйти|приступить|начать)?\s*(?:завтра|сегодня|немедленно|сразу)|могу\s+приступить|начн[уы]|готов\s+(?:завтра|сегодня|сразу))/i;

testTexts.forEach((text, i) => {
    console.log(`\n${i+1}. "${text}"`);
    
    const jobMatch = text.match(improvedJobSearchRegex);
    const readyMatch = text.match(improvedReadyRegex);
    
    if (jobMatch) {
        console.log(`   🔍 Поиск работы: "${jobMatch[0]}"`);
    }
    
    if (readyMatch) {
        console.log(`   ⏱️ Готовность: "${readyMatch[0]}"`);
    }
    
    if (!jobMatch && !readyMatch) {
        console.log(`   ❌ Ничего не найдено`);
    }
});