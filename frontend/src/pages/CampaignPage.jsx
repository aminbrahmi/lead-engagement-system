// src/pages/CampaignPage.jsx
import CampaignForm from "../components/CampaignForm";

export default function CampaignPage({ onLaunch, onViewCampaign, onDeleteCampaign, isRunning, campaigns, campaignsLoading }) {
  return (
    <CampaignForm
      onLaunch={onLaunch}
      onViewCampaign={onViewCampaign}
      onDeleteCampaign={onDeleteCampaign}
      isRunning={isRunning}
      campaigns={campaigns}
      campaignsLoading={campaignsLoading}
    />
  );
}
