import express from "express";

import {
  generateTrustScore
} from "../controllers/trustscore.js";

const router = express.Router();

router.post("/", generateTrustScore);

export default router;