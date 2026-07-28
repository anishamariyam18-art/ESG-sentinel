import express from "express";

import {
  verifyClaim
} from "../controllers/verification.js";

const router = express.Router();

router.post("/", verifyClaim);

export default router;