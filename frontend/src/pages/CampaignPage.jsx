// src/pages/CampaignPage.jsx
import CampaignForm from "../components/CampaignForm";

export default function CampaignPage({ onLaunch, onViewCampaign, isRunning, campaigns, campaignsLoading }) {
  return (
    <CampaignForm
      onLaunch={onLaunch}
      onViewCampaign={onViewCampaign}
      isRunning={isRunning}
      campaigns={campaigns}
      campaignsLoading={campaignsLoading}
    />
  );
}
