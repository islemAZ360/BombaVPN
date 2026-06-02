document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('stars-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d', { alpha: false }); 

    let width, height, centerX, centerY;
    let nodes = [];
    let planets = [];
    let nebulas = [];
    let dataStreams = [];
    let radarRadius = 0;
    let lightningFlash = 0;
    
    // Parallax & Warp Speed controls
    let mouse = { screenX: -1000, screenY: -1000, targetX: 0, targetY: 0, currentX: 0, currentY: 0 };
    let isWarping = false;
    let warpSpeed = 1; // Base speed
    
    const colors = {
        bg: '#0a0e1a',
        neonGreen: 'rgba(0, 255, 204, 1)',
        neonGreenFaint: 'rgba(0, 255, 204, 0.1)',
        cyan: 'rgba(0, 204, 255, 0.3)',
        nebula1: 'rgba(0, 60, 80, 0.15)',
        nebula2: 'rgba(0, 255, 204, 0.05)'
    };

    function resize() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
        centerX = width / 2;
        centerY = height / 2;
        initElements();
    }

    window.addEventListener('resize', resize);
    
    // Mouse Interaction
    window.addEventListener('mousemove', (e) => {
        mouse.screenX = e.clientX;
        mouse.screenY = e.clientY;
        mouse.targetX = (e.clientX - centerX) * 0.5;
        mouse.targetY = (e.clientY - centerY) * 0.5;
    });

    window.addEventListener('mouseout', () => {
        mouse.screenX = -1000;
        mouse.screenY = -1000;
        mouse.targetX = 0;
        mouse.targetY = 0;
        isWarping = false;
    });

    // window.addEventListener('mousedown', () => isWarping = true);
    // window.addEventListener('mouseup', () => isWarping = false);

    // Touch Interaction
    window.addEventListener('touchmove', (e) => {
        if(e.touches.length > 0) {
            mouse.screenX = e.touches[0].clientX;
            mouse.screenY = e.touches[0].clientY;
            mouse.targetX = (e.touches[0].clientX - centerX) * 0.5;
            mouse.targetY = (e.touches[0].clientY - centerY) * 0.5;
        }
    }, { passive: true });

    // window.addEventListener('touchstart', () => isWarping = true, { passive: true });
    window.addEventListener('touchend', () => {
        mouse.screenX = -1000;
        mouse.screenY = -1000;
        mouse.targetX = 0;
        mouse.targetY = 0;
        isWarping = false;
    });

    class Node {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.z = Math.random() * 2 + 0.8; 
            this.vx = (Math.random() - 0.5) * 0.2;
            this.vy = (Math.random() - 0.5) * 0.2;
            this.radius = (Math.random() * 1.5 + 0.5) / this.z;
            this.baseAlpha = Math.random() * 0.5 + 0.2;
        }

        update() {
            // Apply warp speed multiplier
            this.x += (this.vx / this.z) * warpSpeed;
            this.y += (this.vy / this.z) * warpSpeed;

            // Warp effect: pull towards edges when fast
            if (warpSpeed > 2) {
                let dx = this.x - centerX;
                let dy = this.y - centerY;
                this.x += dx * 0.01 * warpSpeed;
                this.y += dy * 0.01 * warpSpeed;
            }

            if (this.x < -100) this.x = width + 100;
            if (this.x > width + 100) this.x = -100;
            if (this.y < -100) this.y = height + 100;
            if (this.y > height + 100) this.y = -100;
        }

        draw(px, py) {
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;

            ctx.fillStyle = `rgba(255, 255, 255, ${this.baseAlpha})`;
            ctx.beginPath();
            
            // Stretch nodes into lines during warp speed
            if (warpSpeed > 2) {
                let stretchX = (drawX - centerX) * 0.05 * warpSpeed;
                let stretchY = (drawY - centerY) * 0.05 * warpSpeed;
                ctx.moveTo(drawX, drawY);
                ctx.lineTo(drawX - stretchX, drawY - stretchY);
                ctx.strokeStyle = `rgba(0, 255, 204, ${this.baseAlpha})`;
                ctx.lineWidth = this.radius;
                ctx.stroke();
            } else {
                ctx.arc(drawX, drawY, this.radius, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    class Nebula {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.radius = Math.random() * 600 + 300;
            this.vx = (Math.random() - 0.5) * 0.05;
            this.vy = (Math.random() - 0.5) * 0.05;
            this.z = 5;
            this.color = Math.random() > 0.5 ? colors.nebula1 : colors.nebula2;
        }
        update() {
            this.x += this.vx * (warpSpeed * 0.2);
            this.y += this.vy * (warpSpeed * 0.2);
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
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(drawX, drawY, this.radius, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    const planetImages = [];
    const planetGlows = [
        'rgba(0, 255, 204, 0.5)', 
        'rgba(0, 204, 255, 0.5)', 
        'rgba(255, 100, 200, 0.3)', 
        'rgba(100, 150, 255, 0.3)'  
    ];

    for (let i = 0; i < 4; i++) {
        const img = new Image();
        img.src = `/static/images/planets/planet_${i}.png`; // تأكد من مسار الصور الخاص بك
        planetImages.push(img);
    }

    class Planet {
        constructor(imgIndex) {
            this.reset();
            this.image = planetImages[imgIndex];
            this.glowColor = planetGlows[imgIndex];
            this.glitchTimer = 0;
        }
        reset() {
            const isLeftEdge = Math.random() > 0.5;
            this.x = isLeftEdge ? Math.random() * (width * 0.2) : width - Math.random() * (width * 0.2);
            this.y = Math.random() * height;
            this.z = Math.random() * 1.5 + 0.6; 
            this.radius = (Math.random() * 50 + 20) / this.z; 
            this.vx = (Math.random() - 0.5) * 0.1;
            this.vy = (Math.random() - 0.5) * 0.1;
            this.rotation = Math.random() * Math.PI * 2;
            this.rotationSpeed = (Math.random() - 0.5) * 0.002;
        }
        update() {
            this.x += (this.vx / this.z) * (warpSpeed > 1 ? warpSpeed * 0.5 : 1);
            this.y += (this.vy / this.z) * (warpSpeed > 1 ? warpSpeed * 0.5 : 1);
            this.rotation += this.rotationSpeed * warpSpeed;
            
            // Random Hologram Glitch trigger
            if (Math.random() < 0.002) this.glitchTimer = 15;
            if (this.glitchTimer > 0) this.glitchTimer--;

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
            
            // Glow
            ctx.globalCompositeOperation = 'screen';
            let grad = ctx.createRadialGradient(0, 0, this.radius * 0.5, 0, 0, this.radius * 1.6);
            grad.addColorStop(0, this.glowColor);
            grad.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(0, 0, this.radius * 1.6, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.globalCompositeOperation = 'source-over';
            ctx.rotate(this.rotation);
            ctx.shadowColor = this.glowColor;
            ctx.shadowBlur = 15;
            
            // Hologram Glitch Effect
            if (this.glitchTimer > 0 && Math.random() > 0.3) {
                let offset = (Math.random() - 0.5) * 10;
                ctx.globalAlpha = 0.7;
                // Cyan split
                ctx.shadowColor = 'cyan';
                ctx.drawImage(this.image, -this.radius + offset, -this.radius, this.radius * 2, this.radius * 2);
                // Red/Green split
                ctx.globalCompositeOperation = 'screen';
                ctx.shadowColor = 'lime';
                ctx.drawImage(this.image, -this.radius - offset, -this.radius + offset/2, this.radius * 2, this.radius * 2);
            } else {
                ctx.drawImage(this.image, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            }
            
            ctx.restore();
        }
    }

    class DataStream {
        constructor() { this.reset(); }
        reset() {
            this.active = false;
            if (Math.random() < 0.05) { 
                this.active = true;
                this.x = Math.random() * width;
                this.y = -100;
                this.length = Math.random() * 100 + 50;
                this.speed = Math.random() * 5 + 5;
                this.opacity = Math.random() * 0.5 + 0.1;
            }
        }
        update() {
            if (!this.active) { this.reset(); return; }
            this.y += this.speed * warpSpeed;
            if (this.y > height + this.length) this.active = false;
        }
        draw(px, py) {
            if (!this.active) return;
            const drawX = this.x + px * 0.1; // Minimal parallax for streams
            
            let grad = ctx.createLinearGradient(drawX, this.y, drawX, this.y - this.length);
            grad.addColorStop(0, `rgba(0, 255, 204, ${this.opacity})`);
            grad.addColorStop(1, 'rgba(0, 255, 204, 0)');
            
            ctx.strokeStyle = grad;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(drawX, this.y);
            ctx.lineTo(drawX, this.y - this.length);
            ctx.stroke();
        }
    }

    function initElements() {
        nodes = [];
        planets = [];
        nebulas = [];
        dataStreams = [];

        const area = width * height;
        const numNodes = Math.min(Math.floor(area / 9000), 150); 
        
        for (let i = 0; i < numNodes; i++) nodes.push(new Node());
        for (let i = 0; i < 4; i++) nebulas.push(new Nebula());
        for (let i = 0; i < 6; i++) planets.push(new Planet(i % 4));
        for (let i = 0; i < 15; i++) dataStreams.push(new DataStream());
    }

    function drawRadar() {
        radarRadius += 2 * warpSpeed;
        const maxRadius = Math.max(width, height);
        
        if (radarRadius > maxRadius) radarRadius = 0;

        const opacity = 0.05 * (1 - radarRadius / maxRadius);
        ctx.beginPath();
        ctx.arc(centerX, centerY, radarRadius, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0, 255, 204, ${opacity})`;
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    function animate() {
        // Deep background
        ctx.fillStyle = colors.bg;
        ctx.fillRect(0, 0, width, height);

        // Lightning flash effect
        if (Math.random() < 0.003) {
            lightningFlash = 1.0;
        }
        if (lightningFlash > 0) {
            ctx.fillStyle = `rgba(180, 230, 255, ${lightningFlash * 0.15})`;
            ctx.fillRect(0, 0, width, height);
            lightningFlash -= 0.04;
            // Secondary strike
            if (Math.random() < 0.1 && lightningFlash < 0.5) {
                lightningFlash = 0.7;
            }
        }

        // Smooth Warp Speed transition
        const targetWarp = isWarping ? 12 : 1;
        warpSpeed += (targetWarp - warpSpeed) * 0.05;

        mouse.currentX += (mouse.targetX - mouse.currentX) * 0.05;
        mouse.currentY += (mouse.targetY - mouse.currentY) * 0.05;
        
        const px = mouse.currentX * -1;
        const py = mouse.currentY * -1;

        // 1. Nebulas
        for (let n of nebulas) { n.update(); n.draw(px, py); }

        // 2. Radar Sweep
        drawRadar();

        // 3. Network Nodes
        ctx.lineWidth = 1;
        for (let i = 0; i < nodes.length; i++) {
            const n1 = nodes[i];
            n1.update();
            
            const x1 = n1.x + px / n1.z;
            const y1 = n1.y + py / n1.z;

            // Connections
            if (warpSpeed < 3) { // Hide connections during hyper-speed for better effect
                for (let j = i + 1; j < nodes.length; j++) {
                    const n2 = nodes[j];
                    const x2 = n2.x + px / n2.z;
                    const y2 = n2.y + py / n2.z;

                    const distSq = (x1 - x2)**2 + (y1 - y2)**2;
                    if (distSq < 22500) { 
                        const opacity = 1 - (Math.sqrt(distSq) / 150);
                        ctx.strokeStyle = `rgba(0, 255, 204, ${opacity * 0.5})`; 
                        ctx.beginPath();
                        ctx.moveTo(x1, y1);
                        ctx.lineTo(x2, y2);
                        ctx.stroke();
                    }
                }
                
                // Mouse Connection
                if (mouse.screenX !== -1000 && mouse.screenY !== -1000) {
                    const mDistSq = (x1 - mouse.screenX)**2 + (y1 - mouse.screenY)**2;
                    if (mDistSq < 40000) {
                        const mOpacity = 1 - (Math.sqrt(mDistSq) / 200);
                        ctx.strokeStyle = `rgba(0, 255, 204, ${mOpacity * 0.8})`;
                        ctx.beginPath();
                        ctx.moveTo(x1, y1);
                        ctx.lineTo(mouse.screenX, mouse.screenY);
                        ctx.stroke();
                    }
                }
            }
            n1.draw(px, py);
        }

        // 4. Planets
        for (let p of planets) { p.update(); p.draw(px, py); }

        // 5. Matrix Data Streams
        for (let d of dataStreams) { d.update(); d.draw(px, py); }

        requestAnimationFrame(animate);
    }

    resize();
    animate();
});
