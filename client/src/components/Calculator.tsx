import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Calculator as CalcIcon, DollarSign, Fuel, Gauge, Search, CheckCircle2, AlertCircle } from "lucide-react";
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
    <Card className="w-full border shadow-lg bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <CardHeader className="pb-4 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <CalcIcon className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-xl">Earnings Calculator</CardTitle>
              <CardDescription>
                {hasRate ? `Rate: $${effectiveRate.toFixed(2)}/mile` : "Select state for rate"}
              </CardDescription>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground font-medium uppercase tracking-wider">Potential Annual Earnings</p>
            <p className="text-3xl font-bold text-primary">
              {hasRate ? `+$${annualNet.toLocaleString(undefined, {maximumFractionDigits: 0})}` : "—"}
            </p>
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="p-6 space-y-8">
        {/* State Selector */}
        {onStateChange && (
          <div className="pb-4 border-b">
            <InlineStateSelector 
              selectedState={selectedState} 
              onStateChange={onStateChange}
              showLabel={true}
            />
          </div>
        )}

        {/* Summary Footer */}
        <div className="space-y-4 pb-6 border-b">
          <div className="grid grid-cols-2 gap-4 text-sm text-center">
            <div className="space-y-1">
              <span className="text-muted-foreground block">Weekly Reimbursement</span>
              <span className="font-semibold text-lg">
                {hasRate ? `$${weeklyReimbursement.toFixed(2)}` : "—"}
              </span>
            </div>
            <div className="space-y-1">
              <span className="text-muted-foreground block">Est. Gas Cost</span>
              <span className="font-semibold text-lg text-destructive">-${weeklyGasCost.toFixed(2)}</span>
            </div>
          </div>
          <div className="bg-muted/50 rounded-lg p-4 flex flex-col items-center justify-center text-center">
            <span className="text-muted-foreground text-sm uppercase tracking-wider font-medium mb-1">Est Net Weekly Payout</span>
            <span className="font-bold text-foreground text-2xl">
              {hasRate ? `$${weeklyNet.toFixed(0)}` : "Select state"}
            </span>
          </div>
        </div>

        {/* Main Slider */}
        <div className="space-y-4">
          <div className="flex justify-between items-end">
            <Label className="text-base font-medium flex items-center gap-2">
              <Gauge className="h-4 w-4 text-muted-foreground" />
              Weekly Miles
            </Label>
            <span className="text-2xl font-bold tabular-nums">{milesPerWeek} <span className="text-sm font-normal text-muted-foreground">mi</span></span>
          </div>
          <Slider 
            value={[milesPerWeek]} 
            onValueChange={(v) => setMilesPerWeek(v[0])} 
            min={100} 
            max={1500} 
            step={50} 
            className="py-2"
          />
        </div>

        {/* Secondary Inputs */}
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-3">
            <Label className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
              <Fuel className="h-4 w-4" />
              Vehicle MPG
            </Label>
            <Input 
              type="number" 
              value={mpg} 
              onChange={(e) => setMpg(Number(e.target.value))} 
              className=""
            />
          </div>
          <div className="space-y-3">
            <Label className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
              <DollarSign className="h-4 w-4" />
              Gas Price
            </Label>
            <Input 
              type="number" 
              value={gasPrice} 
              onChange={(e) => setGasPrice(Number(e.target.value))} 
              className=""
              step="0.01"
            />
          </div>
        </div>

        {/* VIN Lookup */}
        <div className="pt-2">
          <div className="flex gap-2">
            <Input 
              placeholder="Enter VIN to auto-detect MPG (Optional)" 
              value={vin} 
              onChange={(e) => setVin(e.target.value.toUpperCase())} 
              maxLength={17}
              className="flex-1 text-sm"
            />
            <Button 
              onClick={lookupVIN}
              disabled={vinLoading}
              variant="secondary"
              className="shrink-0"
            >
              {vinLoading ? "..." : <Search className="h-4 w-4" />}
            </Button>
          </div>
          {vinLookupStatus === "success" && (
            <p className="text-xs text-emerald-600 mt-2 flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" /> Found vehicle! MPG updated.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
