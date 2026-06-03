document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('stars-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d', { alpha: false }); 

    let width, height, centerX, centerY;
    let stars = [];
    let planets = [];
    let nebulas = [];
    let lightningFlash = 0;
    
    // Parallax & Warp Speed controls
    let mouse = { screenX: -1000, screenY: -1000, targetX: 0, targetY: 0, currentX: 0, currentY: 0 };
    let isWarping = false;
    let warpSpeed = 1; 
    
    const colors = {
        bg: '#05070d', // Deepest space black/blue
        starBase: '255, 255, 255',
        starBlue: '200, 220, 255',
        starYellow: '255, 240, 200',
        nebula1: 'rgba(20, 30, 70, 0.25)', // Deep blue nebula
        nebula2: 'rgba(60, 20, 50, 0.15)', // Deep purple nebula
        nebula3: 'rgba(10, 40, 60, 0.2)'
    };

    function resize() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
        centerX = width / 2;
        centerY = height / 2;
        initElements();
    }

    window.addEventListener('resize', resize);
    
    window.addEventListener('mousemove', (e) => {
        mouse.screenX = e.clientX;
        mouse.screenY = e.clientY;
        mouse.targetX = (e.clientX - centerX) * 0.3; // subtle parallax
        mouse.targetY = (e.clientY - centerY) * 0.3;
    });

    window.addEventListener('mouseout', () => {
        mouse.targetX = 0;
        mouse.targetY = 0;
    });

    window.addEventListener('touchmove', (e) => {
        if(e.touches.length > 0) {
            mouse.screenX = e.touches[0].clientX;
            mouse.screenY = e.touches[0].clientY;
            mouse.targetX = (e.touches[0].clientX - centerX) * 0.3;
            mouse.targetY = (e.touches[0].clientY - centerY) * 0.3;
        }
    }, { passive: true });

    window.addEventListener('touchend', () => {
        mouse.targetX = 0;
        mouse.targetY = 0;
    });

    class Star {
        constructor() {
            this.x = Math.random() * width * 1.2 - width * 0.1;
            this.y = Math.random() * height * 1.2 - height * 0.1;
            this.z = Math.random() * 3 + 0.5; // Depth
            this.radius = (Math.random() * 1.5 + 0.5) / this.z;
            this.vx = (Math.random() - 0.5) * 0.05;
            this.vy = (Math.random() - 0.5) * 0.05;
            this.baseAlpha = Math.random() * 0.8 + 0.2;
            this.twinkleSpeed = Math.random() * 0.02 + 0.01;
            this.twinklePhase = Math.random() * Math.PI * 2;
            
            const colorR = Math.random();
            if (colorR > 0.8) this.color = colors.starBlue;
            else if (colorR > 0.6) this.color = colors.starYellow;
            else this.color = colors.starBase;
        }

        update() {
            this.x += (this.vx / this.z) * warpSpeed;
            this.y += (this.vy / this.z) * warpSpeed;
            this.twinklePhase += this.twinkleSpeed;

            if (warpSpeed > 2) {
                let dx = this.x - centerX;
                let dy = this.y - centerY;
                this.x += dx * 0.005 * warpSpeed;
                this.y += dy * 0.005 * warpSpeed;
            }

            if (this.x < -100) this.x = width + 100;
            if (this.x > width + 100) this.x = -100;
            if (this.y < -100) this.y = height + 100;
            if (this.y > height + 100) this.y = -100;
        }

        draw(px, py) {
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;
            
            const currentAlpha = this.baseAlpha * (0.5 + 0.5 * Math.sin(this.twinklePhase));

            ctx.beginPath();
            
            if (warpSpeed > 2) {
                let stretchX = (drawX - centerX) * 0.02 * warpSpeed;
                let stretchY = (drawY - centerY) * 0.02 * warpSpeed;
                ctx.moveTo(drawX, drawY);
                ctx.lineTo(drawX - stretchX, drawY - stretchY);
                ctx.strokeStyle = `rgba(${this.color}, ${currentAlpha})`;
                ctx.lineWidth = this.radius;
                ctx.stroke();
            } else {
                ctx.fillStyle = `rgba(${this.color}, ${currentAlpha})`;
                ctx.arc(drawX, drawY, this.radius, 0, Math.PI * 2);
                ctx.fill();
                
                // Add soft glow for bigger stars
                if (this.radius > 0.8) {
                    ctx.beginPath();
                    ctx.fillStyle = `rgba(${this.color}, ${currentAlpha * 0.3})`;
                    ctx.arc(drawX, drawY, this.radius * 3, 0, Math.PI * 2);
                    ctx.fill();
                }
            }
        }
    }

    class Nebula {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.radius = Math.random() * 800 + 500;
            this.vx = (Math.random() - 0.5) * 0.02;
            this.vy = (Math.random() - 0.5) * 0.02;
            this.z = Math.random() * 2 + 5; // Far away
            
            const r = Math.random();
            if(r > 0.6) this.color = colors.nebula1;
            else if(r > 0.3) this.color = colors.nebula2;
            else this.color = colors.nebula3;
        }
        update() {
            this.x += this.vx * warpSpeed * 0.1;
            this.y += this.vy * warpSpeed * 0.1;
            if (this.x < -this.radius) this.x = width + this.radius;
            if (this.x > width + this.radius) this.x = -this.radius;
            if (this.y < -this.radius) this.y = height + this.radius;
            if (this.y > height + this.radius) this.y = -this.radius;
        }
        draw(px, py) {
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;
            let grad = ctx.createRadialGradient(drawX, drawY, 0, drawX, drawY, this.radius);
            grad.addColorStop(0, this.color);
            grad.addColorStop(1, 'rgba(0,0,0,0)');
            
            ctx.globalCompositeOperation = 'screen';
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(drawX, drawY, this.radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.globalCompositeOperation = 'source-over';
        }
    }

    const planetImages = [];
    for (let i = 0; i < 9; i++) {
        const img = new Image();
        img.src = `/static/images/planets/planet_${i}.png`; 
        planetImages.push(img);
    }
    
    class Planet {
        constructor(imgIndex) {
            this.reset();
            this.image = planetImages[imgIndex];
        }
        reset() {
            const isLeftEdge = Math.random() > 0.5;
            this.x = isLeftEdge ? Math.random() * (width * 0.2) : width - Math.random() * (width * 0.2);
            this.y = Math.random() * height;
            this.z = Math.random() * 2 + 2; 
            this.radius = (Math.random() * 80 + 30) / this.z; 
            this.vx = (Math.random() - 0.5) * 0.05;
            this.vy = (Math.random() - 0.5) * 0.05;
            this.rotation = Math.random() * Math.PI * 2;
            this.rotationSpeed = (Math.random() - 0.5) * 0.001;
        }
        update() {
            this.x += (this.vx / this.z) * (warpSpeed > 1 ? warpSpeed * 0.5 : 1);
            this.y += (this.vy / this.z) * (warpSpeed > 1 ? warpSpeed * 0.5 : 1);
            this.rotation += this.rotationSpeed * warpSpeed;
            
            if (this.x < -this.radius * 2) this.x = width + this.radius * 2;
            if (this.x > width + this.radius * 2) this.x = -this.radius * 2;
            if (this.y < -this.radius * 2) this.y = height + this.radius * 2;
            if (this.y > height + this.radius * 2) this.y = -this.radius * 2;
        }
        draw(px, py) {
            if (!this.image.complete || this.image.naturalWidth === 0) return;
            
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;

            ctx.save();
            ctx.translate(drawX, drawY);
            
            // Atmospheric subtle glow
            ctx.globalCompositeOperation = 'screen';
            let grad = ctx.createRadialGradient(0, 0, this.radius * 0.8, 0, 0, this.radius * 1.3);
            grad.addColorStop(0, 'rgba(50, 100, 200, 0.2)');
            grad.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(0, 0, this.radius * 1.3, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.globalCompositeOperation = 'source-over';
            ctx.rotate(this.rotation);
            ctx.globalAlpha = 0.8; // Blend slightly with space
            
            ctx.drawImage(this.image, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            
            // Add shadow overlay for realistic lighting
            ctx.rotate(-this.rotation); // unrotate for shadow
            let shadowGrad = ctx.createLinearGradient(-this.radius, -this.radius, this.radius, this.radius);
            shadowGrad.addColorStop(0, 'rgba(0,0,0,0)');
            shadowGrad.addColorStop(0.5, 'rgba(0,0,0,0.3)');
            shadowGrad.addColorStop(1, 'rgba(0,0,0,0.9)');
            ctx.fillStyle = shadowGrad;
            ctx.beginPath();
            ctx.arc(0, 0, this.radius, 0, Math.PI * 2);
            ctx.fill();

            ctx.restore();
        }
    }

    class ShootingStar {
        constructor() { this.reset(); }
        reset() {
            this.active = false;
            if (Math.random() < 0.003) { // rarer, more realistic
                this.active = true;
                this.x = Math.random() * width * 1.5;
                this.y = -100;
                this.length = Math.random() * 200 + 100; 
                this.speed = Math.random() * 20 + 10; 
                this.angle = Math.PI / 4 + (Math.random() - 0.5) * 0.1; 
                this.opacity = Math.random() * 0.5 + 0.5;
            }
        }
        update() {
            if (!this.active) { this.reset(); return; }
            this.x -= Math.cos(this.angle) * this.speed * warpSpeed;
            this.y += Math.sin(this.angle) * this.speed * warpSpeed;
            if (this.x < -this.length || this.y > height + this.length) this.active = false;
        }
        draw(px, py) {
            if (!this.active) return;
            const drawX = this.x + px * 0.2;
            const drawY = this.y + py * 0.2;
            
            const tailX = drawX + Math.cos(this.angle) * this.length;
            const tailY = drawY - Math.sin(this.angle) * this.length;
            
            ctx.save();
            ctx.globalCompositeOperation = 'screen';
            
            let gradOuter = ctx.createLinearGradient(drawX, drawY, tailX, tailY);
            gradOuter.addColorStop(0, `rgba(200, 230, 255, ${this.opacity * 0.8})`);
            gradOuter.addColorStop(0.1, `rgba(100, 180, 255, ${this.opacity * 0.4})`);
            gradOuter.addColorStop(1, 'rgba(0, 0, 0, 0)');
            
            ctx.strokeStyle = gradOuter;
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(drawX, drawY);
            ctx.lineTo(tailX, tailY);
            ctx.stroke();
            
            // Glowing head
            ctx.fillStyle = `rgba(255, 255, 255, ${this.opacity})`;
            ctx.beginPath();
            ctx.arc(drawX, drawY, 2, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.restore();
        }
    }

    let sunImage = new Image(); sunImage.src = '/static/images/planets/sun.png';
    let galaxyImage = new Image(); galaxyImage.src = '/static/images/planets/galaxy.png';
    let blackHoleImage = new Image(); blackHoleImage.src = '/static/images/planets/blackhole.png';

    let sun = { x: width * 0.8, y: height * 0.15, radius: Math.min(width, height) * 0.15, z: 8 };
    let galaxyObj = { x: width * 0.2, y: height * 0.8, radius: Math.min(width, height) * 0.4, z: 10, rot: 0 };
    let shootingStars = [];

    function initElements() {
        stars = [];
        planets = [];
        nebulas = [];
        shootingStars = [];

        const area = width * height;
        const numStars = Math.min(Math.floor(area / 3000), 500); // Many more stars for realism
        
        for (let i = 0; i < numStars; i++) stars.push(new Star());
        for (let i = 0; i < 5; i++) nebulas.push(new Nebula());
        for (let i = 0; i < 4; i++) planets.push(new Planet(i % 9)); 
        for (let i = 0; i < 3; i++) shootingStars.push(new ShootingStar());
        
        sun = { x: width * 0.85, y: height * 0.15, radius: Math.min(width, height) * 0.15, z: 8 };
        galaxyObj = { x: width * 0.2, y: height * 0.85, radius: Math.min(width, height) * 0.4, z: 10, rot: 0 };
    }

    function animate() {
        ctx.globalCompositeOperation = 'source-over';
        ctx.fillStyle = colors.bg;
        ctx.fillRect(0, 0, width, height);

        mouse.currentX += (mouse.targetX - mouse.currentX) * 0.05;
        mouse.currentY += (mouse.targetY - mouse.currentY) * 0.05;
        
        const px = mouse.currentX * -1;
        const py = mouse.currentY * -1;

        // Draw Nebulas (Deep background)
        for (let n of nebulas) { n.update(); n.draw(px, py); }

        // Draw Galaxy
        if (galaxyImage.complete && galaxyImage.naturalWidth > 0) {
            ctx.save();
            const gX = galaxyObj.x + px / galaxyObj.z;
            const gY = galaxyObj.y + py / galaxyObj.z;
            ctx.translate(gX, gY);
            galaxyObj.rot -= 0.0005;
            ctx.rotate(galaxyObj.rot);
            ctx.globalCompositeOperation = 'screen';
            ctx.globalAlpha = 0.4;
            ctx.drawImage(galaxyImage, -galaxyObj.radius, -galaxyObj.radius, galaxyObj.radius*2, galaxyObj.radius*2);
            ctx.restore();
        }

        // Draw Stars
        for (let s of stars) {
            s.update();
            s.draw(px, py);
        }

        // Draw Sun
        if (sunImage.complete && sunImage.naturalWidth > 0) {
            ctx.save();
            const sX = sun.x + px / sun.z;
            const sY = sun.y + py / sun.z;
            ctx.translate(sX, sY);
            ctx.globalCompositeOperation = 'screen';
            ctx.drawImage(sunImage, -sun.radius, -sun.radius, sun.radius*2, sun.radius*2);
            
            // Sun glow
            let grad = ctx.createRadialGradient(0, 0, sun.radius * 0.5, 0, 0, sun.radius * 2.5);
            grad.addColorStop(0, 'rgba(255, 230, 150, 0)');
            grad.addColorStop(0.2, 'rgba(255, 150, 50, 0.4)');
            grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(0, 0, sun.radius * 2.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }

        // Draw Planets
        for (let p of planets) { 
            p.update(); 
            p.draw(px, py); 
        }
        
        // Draw Shooting Stars
        for (let s of shootingStars) { 
            s.update(); 
            s.draw(px, py); 
        }

        requestAnimationFrame(animate);
    }

    resize();
    animate();
});
