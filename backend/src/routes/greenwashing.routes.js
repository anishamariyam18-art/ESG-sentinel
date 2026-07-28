import express from "express";

import {
  detectGreenwashing
} from "../controllers/greenwashing.js";

const router = express.Router();

router.post("/", detectGreenwashing);

export default router;