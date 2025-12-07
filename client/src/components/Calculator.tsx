import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { InlineStateSelector } from "./InlineStateSelector";

type State = "CA" | "WA" | "IL" | "OTHER" | null;

interface CalculatorProps {
  ratePerMile?: number | null;
  selectedState?: State;
  onStateChange?: (state: State) => void;
}

export function Calculator({ ratePerMile = null, selectedState = null, onStateChange }: CalculatorProps) {
  const [milesPerWeek, setMilesPerWeek] = useState(600);
  const [mpg, setMpg] = useState(20);
  const [gasPrice, setGasPrice] = useState(3.16);
  const [vin, setVin] = useState("");
  const [vinLoading, setVinLoading] = useState(false);
  const [vinLookupStatus, setVinLookupStatus] = useState<"idle" | "success" | "error">("idle");

  const lookupVIN = async () => {
    if (vin.length < 17) {
      toast.error("Please enter a valid 17-character VIN");
      return;
    }

    setVinLoading(true);
    setVinLookupStatus("idle");

    try {
      const response = await fetch(
        `https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/${vin}?format=json`
      );
      const data = await response.json();

      if (data.Results && data.Results.length > 0) {
        const results = data.Results;
        const modelYear = results.find((r: any) => r.Variable === "Model Year")?.Value;
        const make = results.find((r: any) => r.Variable === "Make")?.Value;
        const model = results.find((r: any) => r.Variable === "Model")?.Value;

        let estimatedMpg = 20;
        const bodyType = results.find((r: any) => r.Variable === "Body Class")?.Value || "";
        const vehicleType = bodyType.toLowerCase();

        if (vehicleType.includes("truck") || vehicleType.includes("van")) {
          estimatedMpg = 18;
        } else if (vehicleType.includes("suv") || vehicleType.includes("utility")) {
          estimatedMpg = 22;
        } else if (vehicleType.includes("sedan") || vehicleType.includes("car")) {
          estimatedMpg = 26;
        } else if (vehicleType.includes("hybrid")) {
          estimatedMpg = 35;
        }

        setMpg(estimatedMpg);
        setVinLookupStatus("success");
        toast.success(
          `Found: ${modelYear} ${make} ${model} (Est. ${estimatedMpg} MPG)`
        );
      } else {
        setVinLookupStatus("error");
        toast.error("VIN not found. Please check and try again.");
      }
    } catch (error) {
      setVinLookupStatus("error");
      toast.error("Could not look up VIN. Please try again or enter MPG manually.");
    } finally {
      setVinLoading(false);
    }
  };

  const hasRate = ratePerMile !== null;
  const effectiveRate = ratePerMile ?? 0;
  const weeklyReimbursement = milesPerWeek * effectiveRate;
  const weeklyGasCost = (milesPerWeek / mpg) * gasPrice;
  const weeklyNet = weeklyReimbursement - weeklyGasCost;
  const annualNet = weeklyNet * 52;

  return (
    <Card className="w-full rounded-2xl shadow-xl border-0 bg-white">
      <CardContent className="p-6 md:p-8">
        {/* Header Section */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Earnings Calculator</h2>
            <p className="text-sm text-gray-500 mt-1">
              {hasRate ? `Rate: $${effectiveRate.toFixed(2)}/mile` : "Select state for rate"}
            </p>
          </div>
          <div className="sm:text-right">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Potential Annual Earnings</p>
            <p className="text-3xl md:text-4xl font-bold text-primary">
              {hasRate ? `$${annualNet.toLocaleString(undefined, {maximumFractionDigits: 0})}` : "—"}
            </p>
          </div>
        </div>

        {/* Inputs Section */}
        <div className="space-y-6">
          {/* State Selector */}
          {onStateChange && (
            <div>
              <Label className="text-sm font-medium text-gray-700 mb-2 block">Your State</Label>
              <InlineStateSelector 
                selectedState={selectedState} 
                onStateChange={onStateChange}
                showLabel={false}
              />
            </div>
          )}

          {/* Weekly Miles Slider */}
          <div>
            <div className="flex justify-between items-center mb-3">
              <Label className="text-sm font-medium text-gray-700">Weekly Miles</Label>
              <span className="text-lg font-semibold text-gray-900 tabular-nums">
                {milesPerWeek} <span className="text-sm font-normal text-gray-500">mi</span>
              </span>
            </div>
            <Slider 
              value={[milesPerWeek]} 
              onValueChange={(v) => setMilesPerWeek(v[0])} 
              min={100} 
              max={1500} 
              step={50} 
              className="py-1"
            />
          </div>

          {/* MPG and Gas Price - Side by Side */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-sm font-medium text-gray-700 mb-2 block">Vehicle MPG</Label>
              <Input 
                type="number" 
                value={mpg} 
                onChange={(e) => setMpg(Number(e.target.value))} 
                className="h-11"
              />
            </div>
            <div>
              <Label className="text-sm font-medium text-gray-700 mb-2 block">Gas Price</Label>
              <Input 
                type="number" 
                value={gasPrice} 
                onChange={(e) => setGasPrice(Number(e.target.value))} 
                className="h-11"
                step="0.01"
              />
            </div>
          </div>

          {/* VIN Lookup */}
          <div>
            <Label className="text-sm font-medium text-gray-700 mb-2 block">VIN Lookup (Optional)</Label>
            <div className="flex gap-2">
              <Input 
                placeholder="Enter 17-character VIN" 
                value={vin} 
                onChange={(e) => setVin(e.target.value.toUpperCase())} 
                maxLength={17}
                className="flex-1 h-11"
              />
              <Button 
                onClick={lookupVIN}
                disabled={vinLoading}
                variant="secondary"
                className="h-11 px-4"
              >
                {vinLoading ? "..." : <Search className="h-4 w-4" />}
              </Button>
            </div>
            {vinLookupStatus === "success" && (
              <p className="text-xs text-emerald-600 mt-2 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Vehicle found! MPG updated.
              </p>
            )}
          </div>
        </div>

        {/* Results Section */}
        <div className="mt-8 bg-gray-50 rounded-xl p-5">
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <p className="text-xs text-gray-500 mb-1">Weekly Reimbursement</p>
              <p className="text-lg font-semibold text-gray-900">
                {hasRate ? `$${weeklyReimbursement.toFixed(2)}` : "—"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-500 mb-1">Est. Gas Cost</p>
              <p className="text-lg font-semibold text-red-500/80">
                -${weeklyGasCost.toFixed(2)}
              </p>
            </div>
          </div>
          <div className="border-t border-gray-200 pt-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <p className="text-sm font-medium text-gray-600">Est. Net Weekly Payout</p>
              <p className="text-2xl font-bold text-gray-900">
                {hasRate ? `$${weeklyNet.toFixed(0)}` : "Select state"}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
