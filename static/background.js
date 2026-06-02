document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('stars-canvas');
    if (!canvas) return;
    
    // Performance optimization: alpha: false makes the canvas opaque, 
    // we handle the dark background manually inside the animate loop.
    const ctx = canvas.getContext('2d', { alpha: false }); 

    let width, height, centerX, centerY;
    let nodes = [];
    let planets = [];
    let nebulas = [];
    
    // Smooth Parallax tracking
    let mouse = { x: null, y: null, targetX: 0, targetY: 0, currentX: 0, currentY: 0 };
    
    const colors = {
        bg: '#0a0e1a',
        neonGreen: 'rgba(0, 255, 204, 1)',
        cyan: 'rgba(0, 204, 255, 0.3)',
        nebula1: 'rgba(0, 60, 80, 0.15)', // Deep subtle cyan
        nebula2: 'rgba(0, 255, 204, 0.05)' // Ultra faint neon green
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
        // Calculate offset from center of screen
        mouse.targetX = (e.clientX - centerX) * 0.5; // The 0.5 is a sensitivity multiplier
        mouse.targetY = (e.clientY - centerY) * 0.5;
    });

    window.addEventListener('mouseout', () => {
        // Return to center slowly
        mouse.targetX = 0;
        mouse.targetY = 0;
    });

    // Touch support for parallax
    window.addEventListener('touchmove', (e) => {
        if(e.touches.length > 0) {
            mouse.targetX = (e.touches[0].clientX - centerX) * 0.5;
            mouse.targetY = (e.touches[0].clientY - centerY) * 0.5;
        }
    }, { passive: true });

    window.addEventListener('touchend', () => {
        mouse.targetX = 0;
        mouse.targetY = 0;
    });

    class Node {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            // z determines depth. Higher z = further away = moves slower in parallax
            this.z = Math.random() * 2 + 0.8; 
            
            // Base drift speed
            this.vx = (Math.random() - 0.5) * 0.2 / this.z;
            this.vy = (Math.random() - 0.5) * 0.2 / this.z;
            
            this.radius = (Math.random() * 1.5 + 0.5) / this.z;
            this.baseAlpha = Math.random() * 0.5 + 0.2;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;

            // Wrap around screen edges with a margin
            if (this.x < -100) this.x = width + 100;
            if (this.x > width + 100) this.x = -100;
            if (this.y < -100) this.y = height + 100;
            if (this.y > height + 100) this.y = -100;
        }

        draw(px, py) {
            ctx.fillStyle = `rgba(255, 255, 255, ${this.baseAlpha})`;
            ctx.beginPath();
            ctx.arc(this.x + px / this.z, this.y + py / this.z, this.radius, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    class Nebula {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.radius = Math.random() * 600 + 300;
            this.vx = (Math.random() - 0.5) * 0.05;
            this.vy = (Math.random() - 0.5) * 0.05;
            this.z = 5; // Very deep in background
            this.color = Math.random() > 0.5 ? colors.nebula1 : colors.nebula2;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;
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
        'rgba(0, 255, 204, 0.5)',  // Neon Green
        'rgba(0, 204, 255, 0.5)',  // Cyan
        'rgba(255, 100, 200, 0.3)', // Pinkish
        'rgba(100, 150, 255, 0.3)'  // Blue
    ];

    // Preload planet images safely
    for (let i = 0; i < 4; i++) {
        const img = new Image();
        img.src = `/static/images/planets/planet_${i}.png`;
        planetImages.push(img);
    }

    class Planet {
        constructor(imgIndex) {
            const isLeftEdge = Math.random() > 0.5;
            this.x = isLeftEdge ? Math.random() * (width * 0.2) : width - Math.random() * (width * 0.2);
            this.y = Math.random() * height;
            
            this.z = Math.random() * 1.5 + 0.6; // Foreground depth
            this.radius = (Math.random() * 50 + 20) / this.z; 
            
            this.vx = (Math.random() - 0.5) * 0.1 / this.z;
            this.vy = (Math.random() - 0.5) * 0.1 / this.z;
            
            this.image = planetImages[imgIndex];
            this.glowColor = planetGlows[imgIndex];
            this.rotation = Math.random() * Math.PI * 2;
            this.rotationSpeed = (Math.random() - 0.5) * 0.002;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;
            this.rotation += this.rotationSpeed;
            
            if (this.x < -this.radius * 2) this.x = width + this.radius * 2;
            if (this.x > width + this.radius * 2) this.x = -this.radius * 2;
            if (this.y < -this.radius * 2) this.y = height + this.radius * 2;
            if (this.y > height + this.radius * 2) this.y = -this.radius * 2;
        }

        draw(px, py) {
            if (!this.image.complete || this.image.naturalWidth === 0) return;
            
            // Reverse parallax direction for foreground feel
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;

            ctx.save();
            ctx.translate(drawX, drawY);
            
            // Cyber Glow effect (Radial Gradient)
            ctx.globalCompositeOperation = 'screen';
            let grad = ctx.createRadialGradient(0, 0, this.radius * 0.5, 0, 0, this.radius * 1.6);
            grad.addColorStop(0, this.glowColor);
            grad.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(0, 0, this.radius * 1.6, 0, Math.PI * 2);
            ctx.fill();
            
            // Reset composite operation to draw the solid planet image
            ctx.globalCompositeOperation = 'source-over';
            ctx.rotate(this.rotation);
            
            // Subtle CSS-like drop shadow for depth
            ctx.shadowColor = this.glowColor;
            ctx.shadowBlur = 20;
            
            ctx.drawImage(this.image, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            
            ctx.restore();
        }
    }

    function initElements() {
        nodes = [];
        planets = [];
        nebulas = [];

        // Dynamic density based on screen size to maintain 60fps
        const area = width * height;
        const numNodes = Math.min(Math.floor(area / 10000), 120); 
        
        for (let i = 0; i < numNodes; i++) {
            nodes.push(new Node());
        }

        // Draw 3-4 nebulas for ambient lighting
        for(let i=0; i < 4; i++) {
            nebulas.push(new Nebula());
        }

        // Draw 6 planets
        for (let i = 0; i < 6; i++) {
            planets.push(new Planet(i % 4));
        }
    }

    function animate() {
        // Render Deep Void Background
        ctx.fillStyle = colors.bg;
        ctx.fillRect(0, 0, width, height);

        // Interpolate mouse parallax for smoothness
        mouse.currentX += (mouse.targetX - mouse.currentX) * 0.05;
        mouse.currentY += (mouse.targetY - mouse.currentY) * 0.05;
        
        // Reverse Parallax Offset Calculation
        const px = mouse.currentX * -1;
        const py = mouse.currentY * -1;

        // 1. Draw Nebulas (Deepest Layer)
        for (let n of nebulas) {
            n.update();
            n.draw(px, py);
        }

        // 2. Draw Network Nodes & Connections
        ctx.lineWidth = 1;
        for (let i = 0; i < nodes.length; i++) {
            const n1 = nodes[i];
            n1.update();
            
            // Calculate absolute position on canvas
            const x1 = n1.x + px / n1.z;
            const y1 = n1.y + py / n1.z;

            // Connect nearby nodes
            for (let j = i + 1; j < nodes.length; j++) {
                const n2 = nodes[j];
                const x2 = n2.x + px / n2.z;
                const y2 = n2.y + py / n2.z;

                const dx = x1 - x2;
                const dy = y1 - y2;
                const distSq = dx * dx + dy * dy;

                // Threshold distance (150px squared = 22500)
                if (distSq < 22500) { 
                    const dist = Math.sqrt(distSq);
                    const opacity = 1 - (dist / 150);
                    // Network line color - Neon Green
                    ctx.strokeStyle = `rgba(0, 255, 204, ${opacity * 0.6})`; 
                    ctx.beginPath();
                    ctx.moveTo(x1, y1);
                    ctx.lineTo(x2, y2);
                    ctx.stroke();
                }
            }
            n1.draw(px, py);
        }

        // 3. Draw Planets (Foreground Layer)
        for (let p of planets) {
            p.update();
            p.draw(px, py);
        }

        requestAnimationFrame(animate);
    }

    // Initialize and start animation loop
    resize();
    animate();
});
