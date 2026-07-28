export const calculateTrustScore = (
  environmentalScore,
  socialScore,
  governanceScore
) => {

  const overallScore =
    (
      environmentalScore +
      socialScore +
      governanceScore
    ) / 3;

  return Number(
    overallScore.toFixed(2)
  );
};