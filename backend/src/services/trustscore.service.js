import prisma from "../config/prisma.js";

export const createTrustScore = async (data) => {
  return await prisma.trustScore.create({
    data
  });
};

export const getTrustScores = async () => {
  return await prisma.trustScore.findMany();
};