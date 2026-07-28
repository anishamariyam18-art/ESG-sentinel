import express from "express";

import {
  extractClaim,
  fetchClaims
} from "../controllers/claim.js";

const router = express.Router();

router.post("/", extractClaim);

router.get("/", fetchClaims);

export default router;