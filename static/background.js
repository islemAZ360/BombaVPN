/* =====================================================================
   GalaxyVPN — خلفية فضائية تفاعلية (نسخة مُحسّنة)
   • لوحة ألوان موحَّدة مع واجهة التركوازي (#00ffcc)
   • تظليل كروي ثلاثي الأبعاد للكواكب + هالة غلاف جوي + عمق
   • سُدُم ناعمة، شهب مصقولة، vignette لإبراز المحتوى
   • أداء عالٍ عبر sprites مُسبقة الرسم (لا gradients كل إطار)
   • يحترم prefers-reduced-motion ويتوقف عند إخفاء التبويب
   ===================================================================== */
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('stars-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: false });
    const TWO_PI = Math.PI * 2;
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // حد أقصى لكثافة البكسل: على شاشات DPI عالية يصبح الـcanvas ضخماً ويُبطّئ كل blend.
    // 1.0 = حجم CSS الفعلي (الأسرع ويمنع اللاج).
    const DPR = 1; // تم إرجاعها إلى 1 لتسريع الأداء ومنع اللاج

    let width, height, centerX, centerY;
    let stars = [], nebulas = [], planets = [], shootingStars = [];
    let blackHoleObj, astronaut, sun, galaxyObj;
    let bgSprite = null, vignetteSprite = null;
    let zSortedDrawList = null; 
    let running = true;

    let mouse = { screenX: -9999, screenY: -9999, targetX: 0, targetY: 0, currentX: 0, currentY: 0 };

    // --- لوحة ألوان كونية متناغمة مع التركوازي ---
    const RGB = {
        teal:   '0, 255, 204',
        cyan:   '120, 230, 255',
        blue:   '70, 140, 235',
        violet: '140, 95, 225',
        warm:   '255, 208, 150',
        white:  '235, 245, 255'
    };
    const STAR_COLORS = ['#ffffff', '#ffffff', '#eaf6ff', '#a9f7ec', '#a9d0ff', '#ffe6c2'];
    const SHADE_BASE_ANGLE = 0; // زاوية الظل معدلة لليمين

    /* ===================== صور الأصول ===================== */
    const PLANET_IMG_COUNT = 9;
    const planetImages = [];
    for (let i = 0; i < PLANET_IMG_COUNT; i++) {
        const img = new Image();
        img.src = `/static/images/planets/planet_${i}.png`;
        planetImages.push(img);
    }
    const sunImage = new Image();        sunImage.src = '/static/images/planets/sun.png';
    const galaxyImage = new Image();     galaxyImage.src = '/static/images/planets/galaxy.png';
    const astronautImage = new Image();  astronautImage.src = '/static/images/planets/astronaut.png';
    const blackholeImage = new Image();  blackholeImage.src = '/static/images/planets/blackhole.png';
    const nebulaImage = new Image();     nebulaImage.src = '/static/images/planets/nebula_cloud.png';

    /* ===================== sprites مُسبقة الرسم ===================== */
    const glowSprites = {};
    function buildGlowSprite(rgb, maxAlpha) {
        const size = 128; // تقليل الحجم للأداء
        const c = document.createElement('canvas');
        c.width = c.height = size;
        const g = c.getContext('2d');
        const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        grad.addColorStop(0,    `rgba(${rgb},${maxAlpha})`);
        grad.addColorStop(0.30, `rgba(${rgb},${maxAlpha * 0.42})`);
        grad.addColorStop(0.65, `rgba(${rgb},${maxAlpha * 0.10})`);
        grad.addColorStop(1,    `rgba(${rgb},0)`);
        g.fillStyle = grad;
        g.fillRect(0, 0, size, size);
        return c;
    }

    // sprite تظليل كروي ثلاثي الأبعاد محسّن وواقعي (بدون قطع دائري لكي لا يفسد الحلقات)
    let shadeSprite = null;
    function buildShadeSprite() {
        const size = 512;
        const c = document.createElement('canvas');
        c.width = c.height = size;
        const g = c.getContext('2d');
        
        // الضوء يأتي من اليمين (الزاوية 0). اليسار مظلم.
        // تدرج خطي يغطي كامل المربع لكي يظلل الكوكب وحلقاته بنعومة
        const grad = g.createLinearGradient(0, size/2, size, size/2);
        grad.addColorStop(0, 'rgba(0, 0, 0, 0.95)'); // الجانب المظلم
        grad.addColorStop(0.35, 'rgba(0, 0, 0, 0.85)');
        grad.addColorStop(0.55, 'rgba(0, 0, 0, 0.45)');
        grad.addColorStop(0.75, 'rgba(0, 0, 0, 0.05)');  
        grad.addColorStop(1, 'rgba(0, 0, 0, 0)'); // الجانب المضيء
        
        g.fillStyle = grad;
        g.fillRect(0, 0, size, size);
        
        return c;
    }

    // قُرص لمعان (specular) صغير يضيف بريقاً على الجهة المضيئة
    let specSprite = null;
    function buildSpecSprite() {
        const size = 128;
        const c = document.createElement('canvas');
        c.width = c.height = size;
        const g = c.getContext('2d');
        const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        grad.addColorStop(0, 'rgba(255,255,255,0.5)');
        grad.addColorStop(0.5, 'rgba(180,240,255,0.12)');
        grad.addColorStop(1, 'rgba(180,240,255,0)');
        g.fillStyle = grad;
        g.fillRect(0, 0, size, size);
        return c;
    }

    // توهج شمسي مخصّص (كورونا ناعمة + قلب ساطع — بدون أشعة صليبية)
    let sunGlowSprite = null;
    function buildSunGlowSprite() {
        const size = 512;
        const c = document.createElement('canvas');
        c.width = c.height = size;
        const g = c.getContext('2d');
        const cx = size / 2, cy = size / 2;

        // كورونا واسعة دافئة
        const grad1 = g.createRadialGradient(cx, cy, 0, cx, cy, size * 0.5);
        grad1.addColorStop(0, 'rgba(255, 240, 200, 0.95)');
        grad1.addColorStop(0.08, 'rgba(255, 200, 100, 0.70)');
        grad1.addColorStop(0.22, 'rgba(255, 150, 50, 0.32)');
        grad1.addColorStop(0.50, 'rgba(255, 100, 20, 0.08)');
        grad1.addColorStop(1, 'rgba(255, 60, 0, 0)');
        g.fillStyle = grad1;
        g.fillRect(0, 0, size, size);

        // هالة بيضاء مركزية ساطعة
        const grad2 = g.createRadialGradient(cx, cy, 0, cx, cy, size * 0.14);
        grad2.addColorStop(0, 'rgba(255, 255, 255, 1)');
        grad2.addColorStop(0.5, 'rgba(255, 255, 230, 0.55)');
        grad2.addColorStop(1, 'rgba(255, 220, 160, 0)');
        g.globalCompositeOperation = 'screen';
        g.fillStyle = grad2;
        g.beginPath();
        g.arc(cx, cy, size * 0.14, 0, TWO_PI);
        g.fill();

        return c;
    }

    // سُدُم: نُجهّز نسخة إجرائية مضمونة، ثم نستبدلها بنسخة من الصورة عند تحميلها
    let nebulaSprites = [];
    function buildProceduralNebula(rgb) {
        const s = 512;
        const c = document.createElement('canvas');
        c.width = c.height = s;
        const g = c.getContext('2d');
        for (let k = 0; k < 6; k++) {
            const bx = s * (0.28 + Math.random() * 0.44);
            const by = s * (0.28 + Math.random() * 0.44);
            const br = s * (0.16 + Math.random() * 0.22);
            const grad = g.createRadialGradient(bx, by, 0, bx, by, br);
            grad.addColorStop(0, `rgba(${rgb},0.42)`);
            grad.addColorStop(1, `rgba(${rgb},0)`);
            g.fillStyle = grad;
            g.beginPath();
            g.arc(bx, by, br, 0, TWO_PI);
            g.fill();
        }
        return c;
    }
    function buildImageNebula(rgb) {
        const s = 512;
        const c = document.createElement('canvas');
        c.width = c.height = s;
        const g = c.getContext('2d');
        g.drawImage(nebulaImage, 0, 0, s, s);
        // تلوين السحابة (multiply) مع إبقاء الأسود أسود
        g.globalCompositeOperation = 'multiply';
        g.fillStyle = `rgb(${rgb})`;
        g.fillRect(0, 0, s, s);
        // إعادة قناع الشفافية الأصلي (يدعم الصور ذات/بدون alpha)
        g.globalCompositeOperation = 'destination-in';
        g.drawImage(nebulaImage, 0, 0, s, s);
        return c;
    }

    function buildSprites() {
        glowSprites.teal   = buildGlowSprite(RGB.teal, 0.9);
        glowSprites.cyan   = buildGlowSprite(RGB.cyan, 0.9);
        glowSprites.blue   = buildGlowSprite(RGB.blue, 0.85);
        glowSprites.violet = buildGlowSprite(RGB.violet, 0.8);
        glowSprites.warm   = buildGlowSprite(RGB.warm, 0.85);
        glowSprites.white  = buildGlowSprite(RGB.white, 0.95);
        shadeSprite = buildShadeSprite();
        specSprite = buildSpecSprite();
        sunGlowSprite = buildSunGlowSprite();
        if (!nebulaSprites.length) {
            nebulaSprites = [
                buildProceduralNebula(RGB.teal),
                buildProceduralNebula(RGB.blue),
                buildProceduralNebula(RGB.violet)
            ];
        }
    }
    // ترقية السُّدُم لنسخة الصورة فور تحميلها
    nebulaImage.addEventListener('load', () => {
        if (nebulaImage.naturalWidth > 0) {
            nebulaSprites = [
                buildImageNebula(RGB.teal),
                buildImageNebula(RGB.blue),
                buildImageNebula(RGB.violet)
            ];
        }
    });

    /* ===================== الأحداث ===================== */
    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', (e) => {
        mouse.screenX = e.clientX;
        mouse.screenY = e.clientY;
        mouse.targetX = (e.clientX - centerX) * 0.10;
        mouse.targetY = (e.clientY - centerY) * 0.10;
    });
    window.addEventListener('mouseout', () => {
        mouse.targetX = 0; mouse.targetY = 0;
        mouse.screenX = -9999; mouse.screenY = -9999;
    });
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            running = false;
        } else if (!prefersReduced) {
            running = true;
            requestAnimationFrame(animate);
        }
    });

    /* ===================== الكائنات ===================== */
    class Star {
        constructor() { this.reset(true); }
        reset(initial) {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.z = Math.random() * 3 + 1;                       // العمق (1 قريب → 4 بعيد)
            this.size = Math.random() < 0.86 ? 1 : (Math.random() < 0.7 ? 1.6 : 2.4);
            this.color = STAR_COLORS[Math.floor(Math.random() * STAR_COLORS.length)];
            this.vx = (Math.random() - 0.5) * 0.004;
            this.vy = (Math.random() - 0.5) * 0.004;
            this.twinkleSpeed = Math.random() * 0.02 + 0.008;
            this.twinklePhase = Math.random() * TWO_PI;
            this.hero = Math.random() < 0.018;                    // نجوم «بطلة» لامعة
        }
        update() {
            this.x += this.vx / this.z;
            this.y += this.vy / this.z;
            this.twinklePhase += this.twinkleSpeed;
            if (this.x < -10) this.x = width + 10;
            if (this.x > width + 10) this.x = -10;
            if (this.y < -10) this.y = height + 10;
            if (this.y > height + 10) this.y = -10;
        }
        draw(px, py) {
            const dx = this.x + px / this.z;
            const dy = this.y + py / this.z;
            const alpha = 0.35 + Math.abs(Math.sin(this.twinklePhase)) * 0.65;
            ctx.globalCompositeOperation = 'screen';
            if (this.hero) {
                ctx.globalAlpha = alpha * 0.45;
                const gr = 10 + this.size * 4;
                ctx.drawImage(glowSprites.white, dx - gr, dy - gr, gr * 2, gr * 2);
            }
            ctx.globalAlpha = alpha;
            ctx.fillStyle = this.color;
            ctx.fillRect(dx, dy, this.size, this.size);
        }
    }

    class Nebula {
        constructor(i) {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.radius = Math.random() * 380 + 320;
            this.vx = (Math.random() - 0.5) * 0.012;
            this.vy = (Math.random() - 0.5) * 0.012;
            this.spriteIndex = i % 3;
            this.alpha = Math.random() * 0.14 + 0.12;
        }
        update() {
            this.x += this.vx;
            this.y += this.vy;
            const r = this.radius;
            if (this.x < -r) this.x = width + r;
            if (this.x > width + r) this.x = -r;
            if (this.y < -r) this.y = height + r;
            if (this.y > height + r) this.y = -r;
        }
        draw(px, py) {
            const sprite = nebulaSprites[this.spriteIndex];
            if (!sprite) return;
            const dx = this.x + px * 0.04 - this.radius;
            const dy = this.y + py * 0.04 - this.radius;
            ctx.globalCompositeOperation = 'screen';
            ctx.globalAlpha = this.alpha;
            ctx.drawImage(sprite, dx, dy, this.radius * 2, this.radius * 2);
        }
    }

    class Planet {
        constructor(imgIndex, tint) {
            this.image = planetImages[imgIndex];
            this.tint = tint;
            this.reset();
        }
        reset() {
            this.x = Math.random() > 0.5 ? Math.random() * 320 : width - Math.random() * 320;
            this.y = Math.random() * height;
            this.z = Math.random() * 3.5 + 1.5;                   // 1.5 قريب جداً → 5.0 بعيد جداً
            this.radius = (Math.random() * 52 + 34) / (this.z * 0.6);
            this.vx = (Math.random() - 0.5) * 0.02;
            this.vy = (Math.random() - 0.5) * 0.02;
            this.rotation = Math.random() * TWO_PI;
            this.rotationSpeed = (Math.random() - 0.5) * 0.0016;
            // عمق: الكواكب القريبة واضحة جداً والأبعد يقل وضوحها بشدة لزيادة الواقعية
            this.bodyAlpha = Math.max(0.15, Math.min(1, 1.35 - this.z * 0.25));
        }
        update() {
            this.x += this.vx / this.z;
            this.y += this.vy / this.z;
            this.rotation += this.rotationSpeed;
            const m = this.radius + 60;
            if (this.x < -m) this.x = width + m;
            if (this.x > width + m) this.x = -m;
            if (this.y < -m) this.y = height + m;
            if (this.y > height + m) this.y = -m;
        }
        draw(px, py) {
            if (!this.image.complete || this.image.naturalWidth === 0) return;
            const dx = this.x + px / this.z;
            const dy = this.y + py / this.z;
            const r = this.radius;
            const a = this.bodyAlpha;

            // هالة الغلاف الجوي
            const halo = glowSprites[this.tint] || glowSprites.teal;
            ctx.globalCompositeOperation = 'screen';
            ctx.globalAlpha = 0.42 * a;
            const hr = r * 1.85;
            ctx.drawImage(halo, dx - hr, dy - hr, hr * 2, hr * 2);

            // استخدام Offscreen Canvas لدمج الظل باحترافية وبطريقة لا تخفي الفضاء أو تشوه الحلقات
            const pSize = r * 2;
            if (!window.planetOffscreenCanvas) {
                window.planetOffscreenCanvas = document.createElement('canvas');
                window.planetOffscreenCtx = window.planetOffscreenCanvas.getContext('2d', { willReadFrequently: true });
            }
            const pCanvas = window.planetOffscreenCanvas;
            const pCtx = window.planetOffscreenCtx;
            
            if (pCanvas.width < pSize) {
                pCanvas.width = pCanvas.height = pSize * 1.5;
            }
            
            pCtx.clearRect(0, 0, pSize, pSize);
            
            // 1. رسم الكوكب بشكل طبيعي
            pCtx.globalCompositeOperation = 'source-over';
            pCtx.globalAlpha = 1.0;
            pCtx.save();
            pCtx.translate(r, r);
            pCtx.rotate(this.rotation);
            pCtx.drawImage(this.image, -r, -r, pSize, pSize);
            pCtx.restore();
            
            // 2. تطبيق الظل بوضعية multiply لدمج الألوان باحترافية مع الحلقات والجسم
            pCtx.globalCompositeOperation = 'multiply';
            const lightAngle = Math.atan2(sun.y - this.y, sun.x - this.x);
            pCtx.save();
            pCtx.translate(r, r);
            pCtx.rotate(lightAngle);
            pCtx.globalAlpha = 1.0; 
            pCtx.drawImage(shadeSprite, -r, -r, pSize, pSize);
            pCtx.restore();

            // 3. الخطوة السحرية: مسح أي ظل تسرّب خارج حدود الكوكب (لكي لا يظهر مربع الظل في الفضاء)
            pCtx.globalCompositeOperation = 'destination-in';
            pCtx.save();
            pCtx.translate(r, r);
            pCtx.rotate(this.rotation);
            pCtx.globalAlpha = 1.0;
            pCtx.drawImage(this.image, -r, -r, pSize, pSize);
            pCtx.restore();

            // 4. بريق خفيف (Specularity)
            const sr = r * 0.5;
            pCtx.globalCompositeOperation = 'screen';
            pCtx.globalAlpha = 0.5;
            pCtx.save();
            pCtx.translate(r, r);
            pCtx.rotate(lightAngle);
            pCtx.drawImage(specSprite, -r * 0.34 - sr, -r * 0.34 - sr, sr * 2, sr * 2);
            pCtx.restore();
            
            pCtx.globalCompositeOperation = 'source-over'; // إعادة الوضع الافتراضي
            
            // 5. رسم النتيجة النهائية على الكانفاس الرئيسي
            ctx.globalCompositeOperation = 'source-over';
            ctx.globalAlpha = a;
            ctx.drawImage(pCanvas, 0, 0, pSize, pSize, dx - r, dy - r, pSize, pSize);

            ctx.globalAlpha = 1;
        }
    }

    class ShootingStar {
        constructor() { this.active = false; this.cooldown = Math.random() * 400 + 80; }
        spawn() {
            this.active = true;
            this.x = Math.random() * width * 1.4 - width * 0.2;
            this.y = -80;
            this.length = Math.random() * 160 + 90;
            this.speed = Math.random() * 8 + 9;
            this.angle = Math.PI / 4 + (Math.random() - 0.5) * 0.4;
            this.opacity = Math.random() * 0.4 + 0.4;
            this.tint = Math.random() < 0.25 ? RGB.cyan : RGB.white;
        }
        update() {
            if (!this.active) {
                if (--this.cooldown <= 0) { this.spawn(); this.cooldown = Math.random() * 500 + 150; }
                return;
            }
            this.x -= Math.cos(this.angle) * this.speed;
            this.y += Math.sin(this.angle) * this.speed;
            if (this.x < -this.length || this.y > height + this.length) this.active = false;
        }
        draw(px, py) {
            if (!this.active) return;
            const dx = this.x + px * 0.08;
            const dy = this.y + py * 0.08;
            const tailX = dx + Math.cos(this.angle) * this.length;
            const tailY = dy - Math.sin(this.angle) * this.length;
            ctx.globalCompositeOperation = 'screen';
            ctx.globalAlpha = this.opacity;
            ctx.strokeStyle = `rgba(${this.tint},0.7)`;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(dx, dy);
            ctx.lineTo(tailX, tailY);
            ctx.stroke();
            ctx.globalAlpha = this.opacity * 0.9;
            // استخدام Math.round لمنع مشاكل Sub-pixel rendering التي تسبب بطء
            ctx.drawImage(glowSprites.white, Math.round(dx - 8), Math.round(dy - 8), 16, 16);
        }
    }

    class Astronaut {
        constructor() {
            this.x = width * 0.72;
            this.y = height * 0.62;
            this.z = 3.6;
            this.vx = 0.028;
            this.vy = -0.018;
            this.rotation = 0;
            this.radius = 78;
        }
        update() {
            this.x += this.vx;
            this.y += this.vy;
            this.rotation += 0.0009;
            if (this.x < -160 || this.x > width + 160) this.vx *= -1;
            if (this.y < -160 || this.y > height + 160) this.vy *= -1;
        }
        draw(px, py) {
            if (!astronautImage.complete || astronautImage.naturalWidth === 0) return;
            const dx = this.x + px / this.z;
            const dy = this.y + py / this.z;
            ctx.save();
            ctx.translate(dx, dy);
            ctx.rotate(this.rotation);
            ctx.globalAlpha = 0.85;
            ctx.drawImage(astronautImage, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            ctx.restore();
            ctx.globalAlpha = 1;
        }
    }

    class BlackHole {
        constructor() {
            this.x = width * 0.24;
            this.y = height * 0.40;
            this.radius = Math.min(width, height) * 0.16;
            this.rotation = 0;
            this.z = 1.6;
        }
        update() { this.rotation -= 0.0018; }
        draw(px, py) {
            if (!blackholeImage.complete || blackholeImage.naturalWidth === 0) return;
            const dx = this.x + px / this.z;
            const dy = this.y + py / this.z;
            const r = this.radius;
            ctx.save();
            ctx.translate(dx, dy);
            // توهج تركوازي/أزرق متناغم بدل البنفسجي
            ctx.globalCompositeOperation = 'screen';
            ctx.globalAlpha = 0.55;
            ctx.drawImage(glowSprites.teal, -r * 1.7, -r * 1.7, r * 3.4, r * 3.4);
            ctx.globalAlpha = 0.30;
            ctx.drawImage(glowSprites.blue, -r * 2.1, -r * 2.1, r * 4.2, r * 4.2);
            // قرص الثقب الأسود
            ctx.globalAlpha = 1;
            ctx.rotate(this.rotation);
            ctx.drawImage(blackholeImage, -r, -r, r * 2, r * 2);
            ctx.restore();
            ctx.globalAlpha = 1;
            ctx.globalCompositeOperation = 'source-over';
        }
    }

    /* ===================== التهيئة ===================== */
    function initElements() {
        stars = []; nebulas = []; planets = []; shootingStars = [];

        const area = width * height;
        const numStars = Math.min(Math.floor(area / 6500), 240);

        for (let i = 0; i < numStars; i++) stars.push(new Star());
        for (let i = 0; i < 3; i++) nebulas.push(new Nebula(i));

        // توزيع ألوان الهالات: غالبية تركوازية/زرقاء + لمسات
        const tints = ['teal', 'blue', 'cyan', 'teal', 'violet', 'blue'];
        const DISPLAY_PLANET_COUNT = 8; // تقليل عدد الكواكب لتخفيف الازدحام واللاق
        for (let i = 0; i < DISPLAY_PLANET_COUNT; i++) planets.push(new Planet(i % PLANET_IMG_COUNT, tints[i % tints.length]));

        for (let i = 0; i < 2; i++) shootingStars.push(new ShootingStar());

        sun = { x: width * 0.86, y: height * 0.16, radius: Math.min(width, height) * 0.085 };
        galaxyObj = { x: width * 0.80, y: height * 0.82, radius: Math.min(width, height) * 0.32, rot: 0, z: 8 };
        blackHoleObj = new BlackHole();
        astronaut = new Astronaut();

        // بناء قائمة الرسم المُرتّبة حسب العمق مرة واحدة (Z لا يتغيّر)
        // أبعد أولاً → أقرب أخيراً
        zSortedDrawList = [
            { z: 6.0, type: 'sun' },
            { z: astronaut.z, type: 'astronaut' }
        ];
        for (const p of planets) zSortedDrawList.push({ z: p.z, type: 'planet', ref: p });
        zSortedDrawList.sort((a, b) => b.z - a.z);
    }

    function buildStaticLayers() {
        // خلفية ثابتة (sprite مُسبق — يُرسم مرة بدل gradient كل إطار)
        const bgC = document.createElement('canvas');
        bgC.width = width; bgC.height = height;
        const bgG = bgC.getContext('2d');
        const grad = bgG.createRadialGradient(centerX, centerY * 0.82, 0, centerX, centerY, Math.max(width, height) * 0.95);
        grad.addColorStop(0, '#0a1428');
        grad.addColorStop(0.5, '#060c1a');
        grad.addColorStop(1, '#02040a');
        bgG.fillStyle = grad;
        bgG.fillRect(0, 0, width, height);
        bgSprite = bgC;

        // vignette ثابتة (sprite مُسبق)
        const vC = document.createElement('canvas');
        vC.width = width; vC.height = height;
        const vG = vC.getContext('2d');
        const vGrad = vG.createRadialGradient(
            centerX, centerY, Math.min(width, height) * 0.34,
            centerX, centerY, Math.max(width, height) * 0.80
        );
        vGrad.addColorStop(0, 'rgba(2,4,10,0)');
        vGrad.addColorStop(1, 'rgba(2,4,10,0.55)');
        vG.fillStyle = vGrad;
        vG.fillRect(0, 0, width, height);
        vignetteSprite = vC;
    }

    function resize() {
        // أبعاد منطقية (CSS) للمسطح المستخدم في كل العمليات الحسابية
        width = window.innerWidth;
        height = window.innerHeight;
        // أبعاد بكسل فعلية للـcanvas (مقيّدة بـDPR)
        canvas.width = Math.round(width * DPR);
        canvas.height = Math.round(height * DPR);
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        // كل الإحداثيات المنطقية تُترجم تلقائياً عبر setTransform
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        centerX = width / 2;
        centerY = height / 2;
        buildStaticLayers();
        initElements();
        if (prefersReduced || !running) renderFrame();
    }

    /* ===================== الرسم ===================== */
    function renderFrame() {
        // الخلفية (sprite ثابت — أسرع بكثير من gradient كل إطار)
        ctx.globalCompositeOperation = 'source-over';
        ctx.globalAlpha = 1;
        ctx.drawImage(bgSprite, 0, 0);

        // بارالاكس ناعم
        mouse.currentX += (mouse.targetX - mouse.currentX) * 0.08;
        mouse.currentY += (mouse.targetY - mouse.currentY) * 0.08;
        const px = -mouse.currentX;
        const py = -mouse.currentY;

        // السُّدُم (أعمق طبقة)
        for (const n of nebulas) { n.update(); n.draw(px, py); }

        // المجرة
        if (galaxyImage.complete && galaxyImage.naturalWidth > 0) {
            ctx.save();
            const gX = galaxyObj.x + px / galaxyObj.z;
            const gY = galaxyObj.y + py / galaxyObj.z;
            ctx.translate(gX, gY);
            galaxyObj.rot -= 0.0004;
            ctx.rotate(galaxyObj.rot);
            ctx.globalCompositeOperation = 'screen';
            ctx.globalAlpha = 0.42;
            ctx.drawImage(galaxyImage, -galaxyObj.radius, -galaxyObj.radius, galaxyObj.radius * 2, galaxyObj.radius * 2);
            ctx.restore();
            ctx.globalAlpha = 1;
        }

        // الثقب الأسود
        blackHoleObj.update();
        blackHoleObj.draw(px, py);

        // النجوم
        for (const s of stars) { s.update(); s.draw(px, py); }
        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';

        // تحديث الكواكب ورائد الفضاء
        for (const p of planets) p.update();
        astronaut.update();

        // رسم العناصر بالترتيب المُسبق حسب العمق (Z-sorting بُني مرة في initElements)
        for (let i = 0; i < zSortedDrawList.length; i++) {
            const item = zSortedDrawList[i];
            if (item.type === 'planet') {
                item.ref.draw(px, py);
            } else if (item.type === 'astronaut') {
                astronaut.draw(px, py);
            } else if (item.type === 'sun') {
                if (sunImage.complete && sunImage.naturalWidth > 0) {
                    ctx.save();
                    ctx.translate(sun.x + px / 6, sun.y + py / 6);
                    ctx.globalCompositeOperation = 'screen';
                    const gr = sun.radius * 4.5;
                    ctx.globalAlpha = 0.85;
                    ctx.drawImage(sunGlowSprite, -gr, -gr, gr * 2, gr * 2);
                    ctx.globalAlpha = 0.3;
                    const gr2 = sun.radius * 7;
                    ctx.drawImage(glowSprites.warm, -gr2, -gr2, gr2 * 2, gr2 * 2);
                    ctx.globalAlpha = 1;
                    ctx.drawImage(sunImage, -sun.radius, -sun.radius, sun.radius * 2, sun.radius * 2);
                    ctx.restore();
                    ctx.globalAlpha = 1;
                    ctx.globalCompositeOperation = 'source-over';
                }
            }
        }

        // الشهب في طبقة أمامية دائماً
        for (const s of shootingStars) { s.update(); s.draw(px, py); }

        // vignette (sprite ثابت)
        ctx.globalCompositeOperation = 'source-over';
        ctx.globalAlpha = 1;
        ctx.drawImage(vignetteSprite, 0, 0);
    }

    function animate() {
        if (!running) return;
        renderFrame();
        requestAnimationFrame(animate);
    }

    /* ===================== الإقلاع ===================== */
    buildSprites();
    resize();
    if (prefersReduced) {
        running = false;
        renderFrame(); // مشهد ثابت أنيق دون حركة
    } else {
        animate();
    }
});
