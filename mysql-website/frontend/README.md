# MySQL Website Frontend

A modern Vue 3 frontend for MySQL's official website.

## Tech Stack

- Vue 3.4+ (Composition API)
- TypeScript
- Vite 5
- Vue Router 4
- Pinia
- Element Plus
- Axios

## Getting Started

### Install dependencies

```bash
npm install
```

### Development

```bash
npm run dev
```

### Build

```bash
npm run build
```

## Project Structure

```
frontend/
├── src/
│   ├── api/          # API services
│   ├── assets/       # Static assets
│   ├── components/   # Reusable components
│   ├── router/       # Vue Router config
│   ├── stores/       # Pinia stores
│   ├── views/        # Page components
│   ├── App.vue
│   └── main.ts
├── index.html
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## Pages

- `/` - Home page
- `/downloads` - Downloads page
- `/docs` - Documentation page
- `/community` - Community page
- `/news` - News page
- `/login` - Login page
- `/register` - Register page

## API Configuration

The API base URL is configured in `src/api/axios.ts`:

```
http://localhost:8080/api/v1
```
