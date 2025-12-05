import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useState } from "react";

type State = "CA" | "WA" | "IL" | "OTHER";

const STATES = [
  "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
  "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
  "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
  "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
  "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
  "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
  "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
  "Wisconsin", "Wyoming"
];

interface StateSelectorProps {
  isOpen: boolean;
  onStateSelect: (state: State) => void;
}

export function StateSelector({ isOpen, onStateSelect }: StateSelectorProps) {
  const [selected, setSelected] = useState<string>("");

  const handleContinue = () => {
    if (!selected) return;
    
    let stateToPass: State = "OTHER";
    if (selected === "California") stateToPass = "CA";
    else if (selected === "Washington") stateToPass = "WA";
    else if (selected === "Illinois") stateToPass = "IL";
    
    onStateSelect(stateToPass);
  };

  return (
    <Dialog open={isOpen} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-md" onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Select Your State</DialogTitle>
          <DialogDescription>
            Select the state where your vehicle is registered to continue.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <Select value={selected} onValueChange={setSelected}>
            <SelectTrigger data-testid="state-selector-trigger">
              <SelectValue placeholder="Choose a state..." />
            </SelectTrigger>
            <SelectContent className="max-h-[200px]">
              {STATES.map((state) => (
                <SelectItem key={state} value={state} data-testid={`state-option-${state}`}>
                  {state}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button 
            onClick={handleContinue}
            disabled={!selected}
            className="w-full bg-primary hover:bg-primary/90"
            data-testid="button-continue-state"
          >
            Continue
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
