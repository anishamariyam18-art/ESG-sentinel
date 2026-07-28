import prisma from "../config/prisma.js";

export const createClaim = async (data) => {
  return await prisma.claim.create({
    data: {
      claimText: data.claimText,
      category: data.category,
      reportId: Number(data.reportId)
    }
  });
};

export const getAllClaims = async () => {
  return await prisma.claim.findMany({
    include: {
      report: true
    }
  });
};