# ESG Sentinel

## Project Description

ESG Sentinel is an AI-powered ESG (Environmental, Social, and Governance) Trust Intelligence Platform. It allows users to upload ESG reports (PDFs), which are analyzed by a dedicated AI service to extract claims, verify them, detect greenwashing, and generate an overall trust score. This repository contains the backend service that handles authentication, report management, and orchestration between the database and the AI analysis server.

## Tech Stack

**Backend**
- Node.js
- Express.js
- PostgreSQL (raw SQL via `pg`, no ORM)
- JWT Authentication
- bcryptjs
- multer
- axios
- dotenv
- cors
- helmet
- morgan
- cookie-parser
- express-validator

**AI Service**
- FastAPI (separate service, not part of this repository)

**Frontend**
- React.js (separate application, not part of this repository)

## Folder Overview