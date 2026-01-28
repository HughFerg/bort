# Bort Search - Production Deployment Plan

## Current State
- Working MVP with search, random, filters, and manual deletion
- 5,343 indexed frames from Season 1 (13 episodes)
- Running locally on FastAPI + LanceDB

---

## Phase 1: Critical Security & Legal (MUST DO FIRST)

### 1.1 Authentication & Authorization
**Current Risk:** Anyone can delete frames from the index

**Solution:**
- Add admin authentication (HTTP Basic Auth or JWT)
- Protect DELETE endpoints with `@requires_auth` decorator
- Environment variable for admin password
- Consider: Simple password gate vs OAuth

**Estimated Time:** 2-3 hours

### 1.2 Rate Limiting
**Current Risk:** API can be spammed

**Solution:**
- Add `slowapi` or `fastapi-limiter`
- Limit searches to 60/minute per IP
- Limit deletions to 10/hour for admin
- Block abusive IPs

**Estimated Time:** 1 hour

### 1.3 Copyright Disclaimer
**Current Risk:** Legal issues with Disney/Fox content

**Solution:**
```markdown
## Disclaimer
This is a research/educational tool. All content is copyright © Disney/Fox.
Hosted under Fair Use for non-commercial purposes.
Contact: [your email] for takedown requests.
```

Add to frontend + `/legal` endpoint

**Estimated Time:** 30 mins

---

## Phase 2: Infrastructure & Deployment

### 2.1 Containerization
Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "search:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `docker-compose.yml` for local testing

**Estimated Time:** 2 hours

### 2.2 Environment Configuration
Move all hardcoded values to `.env`:
```
DATABASE_PATH=data/simpsons.lance
FRAMES_PATH=data/frames
ADMIN_PASSWORD=xxxxx
ALLOWED_ORIGINS=https://yourdomain.com
```

**Estimated Time:** 1 hour

### 2.3 Choose Hosting Platform

#### Option A: Railway (RECOMMENDED)
- Easiest deployment (connects to GitHub)
- Built-in PostgreSQL/Redis if needed
- ~$10-20/month
- No DevOps knowledge required

**Steps:**
1. Push to GitHub
2. Connect Railway to repo
3. Add environment variables
4. Deploy (automatic)

#### Option B: Fly.io
- Good for Python apps
- More control, similar pricing
- Global edge network

#### Option C: DigitalOcean App Platform
- Middle ground between ease and control
- ~$12/month minimum

**Estimated Time:** 2-4 hours (first time)

### 2.4 Static File Hosting
**Problem:** 5,343 frame images = ~500MB-1GB

**Solutions:**
1. **Cloudflare R2** (S3-compatible, $0.015/GB) - RECOMMENDED
   - Upload frames: `aws s3 sync data/frames s3://bucket --endpoint-url=...`
   - Update image URLs in frontend
   - Add CDN for fast delivery

2. **Backblaze B2** ($0.005/GB storage)
3. **AWS S3** (more expensive)

**Estimated Time:** 3-4 hours

---

## Phase 3: Performance & Reliability

### 3.1 Database Migration Options

**Option A: Keep LanceDB** (SIMPLEST)
- Mount volume for persistence
- Backup regularly to S3
- Works great for current scale

**Option B: Hosted Vector DB**
- Pinecone, Weaviate, Qdrant
- More expensive ($70+/month)
- Only needed for >1M vectors

**Recommendation:** Keep LanceDB for now

### 3.2 Caching
Add Redis for:
- Popular search queries
- Stats endpoint
- Session data

**Cost:** $5-10/month (Upstash or Railway)

**Estimated Time:** 3-4 hours

### 3.3 Image Optimization
```bash
# Convert to WebP (80% smaller)
for img in data/frames/**/*.jpg; do
  cwebp "$img" -o "${img%.jpg}.webp" -q 80
done
```

**Estimated Time:** 2 hours + conversion time

---

## Phase 4: Monitoring & Operations

### 4.1 Error Tracking
- Add Sentry (free tier: 5K errors/month)
- Track crashes, slow queries, errors

**Estimated Time:** 1 hour

### 4.2 Analytics
- Plausible Analytics (privacy-friendly)
- Track: searches, popular queries, random usage

**Estimated Time:** 30 mins

### 4.3 Uptime Monitoring
- UptimeRobot (free, checks every 5 mins)
- Email alerts if site goes down

**Estimated Time:** 15 mins

### 4.4 Backups
```bash
# Backup script
tar -czf backup-$(date +%Y%m%d).tar.gz data/
aws s3 cp backup-*.tar.gz s3://backups/
```

Run daily via cron/GitHub Actions

**Estimated Time:** 1 hour

---

## Phase 5: User Experience Polish

### 5.1 Frontend Improvements
- [ ] Loading states (spinner during search)
- [ ] Error messages (better UX for failures)
- [ ] Mobile optimization (test on phone)
- [ ] Keyboard shortcuts (Enter to search, Esc for modal)
- [ ] Share button (copy URL to clipboard)
- [ ] Dark mode toggle

**Estimated Time:** 4-6 hours

### 5.2 SEO & Meta Tags
```html
<meta name="description" content="Search Simpsons scenes by description">
<meta property="og:image" content="/preview.png">
<meta name="twitter:card" content="summary_large_image">
```

**Estimated Time:** 1 hour

### 5.3 Landing Page
Add hero section explaining what the site does

**Estimated Time:** 2 hours

---

## Phase 6: Advanced Features (Optional)

- User accounts (save favorites)
- Permalink for specific frames
- Embed codes
- API for developers
- More seasons
- Subtitle search

---

## Deployment Checklist

### Pre-Launch
- [ ] Add authentication to DELETE endpoint
- [ ] Add rate limiting
- [ ] Add copyright disclaimer
- [ ] Set up error tracking (Sentry)
- [ ] Test on mobile devices
- [ ] Set up backups
- [ ] Configure environment variables
- [ ] Add HTTPS/SSL
- [ ] Test with friends (private beta)

### Launch Day
- [ ] Deploy to production
- [ ] Upload images to R2/CDN
- [ ] Update DNS records
- [ ] Test all features live
- [ ] Monitor errors closely
- [ ] Share on Twitter/Reddit (if desired)

### Post-Launch
- [ ] Monitor usage/costs
- [ ] Fix bugs as reported
- [ ] Collect user feedback
- [ ] Plan next features

---

## Cost Breakdown (Monthly)

### Minimal Setup (~$25/month)
- Railway hosting: $10
- Cloudflare R2 storage: $1
- Domain: $1/month (.com)
- Uptime monitoring: Free
- Error tracking: Free (Sentry)
- CDN: Free (Cloudflare)

### Standard Setup (~$60/month)
- Railway (better resources): $20
- Cloudflare R2: $2
- Redis cache (Upstash): $10
- Better monitoring (DataDog): $15
- Domain: $1
- Email service (SendGrid): $0-15

### At Scale (~$200/month)
- Dedicated server: $100
- Multiple regions: $50
- Advanced monitoring: $30
- CDN bandwidth: $20

---

## Biggest Risk: Copyright

**The Problem:**
The Simpsons is owned by Disney/Fox. Hosting copyrighted content could result in DMCA takedown.

**Options:**

### A. Fair Use Defense (RECOMMENDED)
- Educational/research purpose
- Transformative use (search tool, not streaming)
- Small portion of total content (Season 1 only)
- No commercial use/ads
- Add prominent disclaimers

**Risk:** Medium. Many similar projects exist (Frinkiac, Morbotron)

### B. Limit Scope
- Index only 2-3 episodes as "demo"
- Use lower resolution images
- Add watermarks

**Risk:** Low, but less useful

### C. Seek Permission
- Contact Disney's licensing department
- Explain non-commercial educational use
- Unlikely to succeed, but worth trying

**Risk:** Low (worst case: they say no)

### D. Geographic Restrictions
- Only serve to specific countries with different copyright laws
- Use VPN detection

**Risk:** Medium, technically complex

---

## Recommended Path

### Week 1: Security & Deployment
1. Add authentication (2-3 hours)
2. Add rate limiting (1 hour)
3. Create Dockerfile (2 hours)
4. Deploy to Railway (3 hours)
5. Add disclaimer (30 mins)

**Total:** ~9 hours, $10/month

### Week 2: Files & Performance
1. Upload images to Cloudflare R2 (4 hours)
2. Update frontend for CDN URLs (1 hour)
3. Optimize images to WebP (2 hours)
4. Add basic caching (2 hours)

**Total:** ~9 hours, $11/month

### Week 3: Polish & Monitor
1. Add Sentry error tracking (1 hour)
2. Set up uptime monitoring (15 mins)
3. Mobile testing and fixes (3 hours)
4. Add meta tags/SEO (1 hour)
5. Set up backups (1 hour)

**Total:** ~6 hours

### Week 4: Launch
1. Private beta with friends (1 week)
2. Fix reported bugs
3. Public launch (share on Twitter/Reddit/HN)
4. Monitor and iterate

**Total:** Ongoing

---

## Questions to Answer Before Deployment

1. **Domain name?** bort.search? simpsons-search.com?
2. **Handle DMCA takedowns?** Automated process or manual?
3. **User accounts?** Or keep anonymous?
4. **Monetization?** Keep free or add optional donations?
5. **Scale?** How many users expected? (affects hosting choice)
6. **Time commitment?** 10 hours/week? 2 hours/week?

---

## Next Steps

Would you like me to:
1. **Start with Phase 1** (auth + security)?
2. **Create Dockerfile** for containerization?
3. **Set up Railway deployment**?
4. **Help with copyright disclaimer**?
5. **Something else?**

The fastest path to production is: Auth → Dockerfile → Railway → R2 → Launch (~20 hours total work)
