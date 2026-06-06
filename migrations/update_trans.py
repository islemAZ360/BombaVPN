import ast

def update_translations():
    with open('translations.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We will just do some text replacements to add the new keys
    # English
    en_new = """        'TipClearReceipt': 'Take a <strong>clear picture of the transfer receipt</strong> after completing the payment.',
        'HeroSubtitle': 'Explore the space of the internet with absolute freedom. Unmatched speed, complete security, and easy bypass of restrictions with a single click.',
        'StartNowBtn': 'Start Now / Login',
        'Feature1Title': 'Lightning Fast',
        'Feature1Desc': 'Dedicated V2Ray servers ensure smooth browsing and streaming without interruptions.',
        'Feature2Title': 'Security & Encryption',
        'Feature2Desc': 'We protect your data and privacy with the strongest encryption techniques, so you can browse safely even on public networks.',
        'Feature3Title': 'Support for All Devices',
        'Feature3Desc': 'Our servers work efficiently on all devices: Android, iPhone, and Windows via the V2Ray app.',
        'UnblockedAppsTitle': 'Enjoy freedom of access to all sites and apps',
        'ServersWorldwideTitle': 'Fast servers all over the world'"""
    
    content = content.replace("'TipClearReceipt': 'Take a <strong>clear picture of the transfer receipt</strong> after completing the payment.'", en_new)

    # Arabic
    ar_new = """        'TipClearReceipt': 'قم بالتقاط <strong>صورة واضحة لوصل التحويل (Receipt)</strong> بعد إتمام الدفع.',
        'HeroSubtitle': 'استكشف فضاء الإنترنت بحرية مطلقة. سرعة لا تضاهى، أمان تام، وتجاوز للقيود بكل سهولة وبضغطة زر واحدة.',
        'StartNowBtn': 'ابدأ الآن / تسجيل الدخول',
        'Feature1Title': 'سرعة خارقة',
        'Feature1Desc': 'سيرفرات مخصصة ببروتوكول V2Ray تضمن لك تجربة تصفح ومشاهدة سلسة بدون تقطيع.',
        'Feature2Title': 'أمان وتشفير',
        'Feature2Desc': 'نحمي بياناتك وخصوصيتك بأقوى تقنيات التشفير، لتتصفح بأمان حتى في الشبكات العامة.',
        'Feature3Title': 'دعم لكل الأجهزة',
        'Feature3Desc': 'تعمل السيرفرات لدينا بكفاءة على جميع الأجهزة: أندرويد، آيفون، وويندوز عبر تطبيق V2Ray.',
        'UnblockedAppsTitle': 'استمتع بحرية الوصول إلى جميع المواقع والتطبيقات',
        'ServersWorldwideTitle': 'سيرفرات سريعة في مختلف أنحاء العالم'"""
        
    content = content.replace("'TipClearReceipt': 'قم بالتقاط <strong>صورة واضحة لوصل التحويل (Receipt)</strong> بعد إتمام الدفع.'", ar_new)
    
    # Russian
    ru_new = """        'TipClearReceipt': 'Сделайте <strong>четкое фото чека о переводе</strong> после завершения оплаты.',
        'HeroSubtitle': 'Исследуйте пространство интернета с абсолютной свободой. Непревзойденная скорость, полная безопасность и легкий обход ограничений в один клик.',
        'StartNowBtn': 'Начать сейчас / Войти',
        'Feature1Title': 'Молниеносная скорость',
        'Feature1Desc': 'Выделенные серверы V2Ray обеспечивают плавный просмотр и потоковую передачу без прерываний.',
        'Feature2Title': 'Безопасность и шифрование',
        'Feature2Desc': 'Мы защищаем ваши данные и конфиденциальность с помощью самых надежных методов шифрования.',
        'Feature3Title': 'Поддержка всех устройств',
        'Feature3Desc': 'Наши серверы эффективно работают на всех устройствах: Android, iPhone и Windows через приложение V2Ray.',
        'UnblockedAppsTitle': 'Наслаждайтесь свободным доступом ко всем сайтам и приложениям',
        'ServersWorldwideTitle': 'Быстрые серверы по всему миру'"""
        
    content = content.replace("'TipClearReceipt': 'Сделайте <strong>четкое фото чека о переводе</strong> после завершения оплаты.'", ru_new)

    with open('translations.py', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("translations.py updated")

if __name__ == '__main__':
    update_translations()
