const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = 8080;

// MIME types
const mimeTypes = {
    '.html': 'text/html',
    '.js': 'text/javascript',
    '.css': 'text/css',
    '.json': 'application/json'
};

const server = http.createServer((req, res) => {
    const parsedUrl = url.parse(req.url, true);
    const pathname = parsedUrl.pathname;
    
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }
    
    // API endpoint
    if (pathname === '/api/fetch-tweets' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                const data = JSON.parse(body);
                console.log('Received request:', { username: data.username, listId: data.listId });
                
                // For now, return mock data
                // In real implementation, this would use puppeteer or similar to scrape X
                const mockTweets = [
                    {
                        name: 'Tech Insider',
                        username: 'techinsider',
                        text: 'Breaking: New AI model achieves state-of-the-art results on multiple benchmarks. The model uses a novel architecture that reduces training time by 40%.',
                        created_at: new Date(Date.now() - 3600000).toISOString(),
                        likes: 1234,
                        retweets: 567,
                        replies: 89
                    },
                    {
                        name: 'AI Research',
                        username: 'airesearch',
                        text: 'Just published our latest paper on efficient transformer architectures. Check it out! 📄🧠 #MachineLearning #AI',
                        created_at: new Date(Date.now() - 7200000).toISOString(),
                        likes: 892,
                        retweets: 234,
                        replies: 45
                    },
                    {
                        name: 'Dev News',
                        username: 'devnews',
                        text: 'TypeScript 5.4 is out with exciting new features including improved type inference and faster compilation. Upgrade now!',
                        created_at: new Date(Date.now() - 10800000).toISOString(),
                        likes: 2341,
                        retweets: 890,
                        replies: 123
                    }
                ];
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, tweets: mockTweets }));
            } catch (error) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: false, error: error.message }));
            }
        });
        return;
    }
    
    // Serve static files
    let filePath = pathname === '/' ? '/index.html' : pathname;
    filePath = path.join(__dirname, filePath);
    
    const ext = path.extname(filePath).toLowerCase();
    const contentType = mimeTypes[ext] || 'application/octet-stream';
    
    fs.readFile(filePath, (err, content) => {
        if (err) {
            if (err.code === 'ENOENT') {
                res.writeHead(404, { 'Content-Type': 'text/plain' });
                res.end('File not found');
            } else {
                res.writeHead(500, { 'Content-Type': 'text/plain' });
                res.end('Server error');
            }
        } else {
            res.writeHead(200, { 'Content-Type': contentType });
            res.end(content);
        }
    });
});

server.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running at http://0.0.0.0:${PORT}/`);
});
